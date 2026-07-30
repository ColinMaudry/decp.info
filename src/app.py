# ruff: noqa: E402  -- sys.path manipulation must precede third-party imports
import os
import sys
from pathlib import Path
from shutil import rmtree

# Sur les serveurs où le package est installé en mode éditable, pip peut ajouter
# src/ à sys.path via un fichier .pth. Combiné à la racine du projet (déjà dans
# sys.path via gunicorn), Dash's use_pages enregistre alors chaque page deux fois :
# une fois comme pages.X et une fois comme src.pages.X → erreur "duplicate paths".
_src_dir = str(Path(__file__).parent.resolve())
while _src_dir in sys.path:
    sys.path.remove(_src_dir)

import dash_bootstrap_components as dbc
import pandas  # noqa: F401  # eager import: avoid plotly's lazy-import race across Dash callback threads
import tomllib
from dash import (
    ALL,
    Dash,
    Input,
    Output,
    State,
    callback,
    ctx,
    dcc,
    html,
    page_container,
    page_registry,
)
from dotenv import load_dotenv
from flask import Flask, Response, redirect
from flask_login import current_user

from src.auth.setup import init_auth
from src.utils import DEVELOPMENT
from src.utils.cache import cache
from src.utils.chatwoot import (
    build_identity_script,
    build_reset_script,
    build_widget_script,
    subscription_attributes,
)

load_dotenv()

# if os.getenv("PYTEST_CURRENT_TEST"):
#     os.environ["DATA_FILE_PARQUET_PATH"]

META_TAGS = [
    {"name": "viewport", "content": "width=device-width, initial-scale=1"},
    {
        "name": "keywords",
        "content": "commande publique, decp, marchés publics, données essentielles, colibre",
    },
    # og:title/description/image/twitter:* sont générées par page (register_page),
    # celles-ci sont statiques et communes à toutes les pages.
    {"property": "og:site_name", "content": "colibre"},
    {"property": "og:locale", "content": "fr_FR"},
    {"property": "og:image:width", "content": "1200"},
    {"property": "og:image:height", "content": "630"},
]

if DEVELOPMENT:
    META_TAGS.append({"name": "robots", "content": "noindex"})

# Le cache doit être initialisé AVANT la construction de Dash : `use_pages=True`
# importe les modules de pages pendant l'instanciation, et certains appellent des
# fonctions memoizées (@cache.memoize) dès l'import (ex. tableau.py).
server = Flask(__name__)

cache_dir = os.getenv("CACHE_DIR", "/tmp/colibre-cache")

rmtree(cache_dir, ignore_errors=True)

cache.init_app(
    server,
    config={
        "CACHE_TYPE": "FileSystemCache",
        "CACHE_DIR": cache_dir,
        "CACHE_DEFAULT_TIMEOUT": int(
            os.getenv("CACHE_DEFAULT_TIMEOUT", 3600 * 24)
        ),  # 24h par défaut
        "CACHE_THRESHOLD": 300,
    },
)

_mcp_enabled = os.getenv("DASH_MCP_ENABLED", "").lower() == "true"

app: Dash = Dash(
    server=server,
    # name="src" (et non "src.app") pour que use_pages enregistre les pages sous
    # le namespace `src.pages.*`, identique aux imports inter-pages (ex.
    # inscription.py: `from src.pages.connexion import linkedin_button`). Sinon
    # Dash découvre `pages.connexion` tandis que l'import explicite crée
    # `src.pages.connexion` : deux identités, même URL → "duplicate paths" →
    # check_for_duplicate_pathnames lève à chaque requête → 500 sur toute l'app.
    name="src",
    title="Colibre",
    use_pages=True,
    suppress_callback_exceptions=True,
    compress=True,
    enable_mcp=_mcp_enabled,
    meta_tags=META_TAGS,
)

init_auth(app.server)

# Exempter les routes internes de Dash de la protection CSRF.
# Dash enregistre ses routes directement sur le serveur Flask (pas via blueprint),
# donc on itère la url_map après init_auth pour cibler les bons endpoints.
from src.auth.setup import _csrf as _auth_csrf  # noqa: E402

if _auth_csrf is not None:
    for _rule in app.server.url_map.iter_rules():
        if _rule.rule.startswith("/_dash") or _rule.rule.startswith("/_reload"):
            _vf = app.server.view_functions.get(_rule.endpoint)
            if _vf is not None:
                _auth_csrf.exempt(_vf)

from src.api import init_api  # noqa: E402  # inline: src.db.conn must be ready first

init_api(app.server)

# Serveur MCP (issue #111, scope A) : n'expose QUE les fonctions @mcp_enabled,
# jamais les callbacks/layout/pages d'UI. Activé via DASH_MCP_ENABLED=true.
if _mcp_enabled:
    from dash.mcp import configure_mcp_server  # noqa: E402

    configure_mcp_server(
        include_layout=False,
        include_callbacks=False,
        include_pages=False,
        include_clientside_callbacks=False,
    )
    import src.mcp.tools  # noqa: E402,F401  # l'import enregistre les @mcp_enabled

    # Les routes /_mcp existent maintenant : exempter du CSRF (POST JSON-RPC
    # externe sans jeton) puis brancher le garde d'abonnement.
    from src.mcp.auth import init_mcp_auth  # noqa: E402

    if _auth_csrf is not None:
        for _rule in app.server.url_map.iter_rules():
            if _rule.rule.startswith("/_mcp"):
                _vf = app.server.view_functions.get(_rule.endpoint)
                if _vf is not None:
                    _auth_csrf.exempt(_vf)

    init_mcp_auth(app.server)

    # Serveur d'autorisation OAuth 2.1 (scope B2, #114) : découverte, DCR,
    # authorize/token, révocation. Réutilise la session flask_login.
    from src.mcp import usage  # noqa: E402
    from src.mcp.oauth import routes as oauth_routes  # noqa: E402
    from src.mcp.oauth import store as oauth_store  # noqa: E402

    _users_db = os.environ["USERS_DB_PATH"]
    oauth_store.init_schema(_users_db)
    usage.init_schema(_users_db)
    usage.purge_older_than(_users_db)

    oauth_routes.init_oauth(app.server)

    # Exempter du CSRF les endpoints OAuth machine-à-machine (POST externes sans
    # cookie) et les documents de découverte (GET). /oauth/authorize N'EST PAS
    # exempté : endpoint de consentement authentifié par cookie de session, donc
    # protégé par CSRF via un jeton dans le formulaire de consentement.
    if _auth_csrf is not None:
        _csrf_exempt_oauth = ("/oauth/token", "/oauth/register", "/oauth/revoke")
        for _rule in app.server.url_map.iter_rules():
            if _rule.rule in _csrf_exempt_oauth or _rule.rule.startswith(
                "/.well-known/"
            ):
                _vf = app.server.view_functions.get(_rule.endpoint)
                if _vf is not None:
                    _auth_csrf.exempt(_vf)

from src.subscriptions.setup import init_subscriptions  # noqa: E402

init_subscriptions(app.server)

from src.saved_views import db as saved_views_db  # noqa: E402

saved_views_db.init_schema()

from src.roadmap import db as roadmap_db  # noqa: E402

roadmap_db.init_schema()

from src.mcp.account import mcp_account_bp  # noqa: E402

app.server.register_blueprint(mcp_account_bp)

# Pages SEO rendues côté serveur (voir src/seo/routes.py). Enregistrées avant
# init_not_found pour être de vraies règles Flask, donc hors du catch-all Dash.
from src.seo.routes import seo_bp  # noqa: E402

app.server.register_blueprint(seo_bp)

# 404 sur les chemins qui ne correspondent à aucune page (#125). À déclarer
# après les autres routes : le garde ne s'applique qu'au catch-all de Dash, donc
# toute route enregistrée ici ou plus haut lui échappe par construction.
from src.not_found import init_not_found  # noqa: E402

init_not_found(app.server)


# robots.txt
def _build_robots_txt(development: bool) -> str:
    """Contenu du robots.txt, selon l'environnement.

    Les instances non-prod (test.colibre.fr, dev) sont interdites d'indexation
    dans leur intégralité, pour ne pas concurrencer colibre.fr dans les résultats
    de recherche avec du contenu dupliqué. Complète la meta `robots: noindex`
    ajoutée aux META_TAGS : le Disallow empêche l'exploration, la meta empêche
    l'indexation des URLs découvertes par ailleurs (liens entrants).
    """
    if development:
        return """
User-agent: *
Disallow: /
"""
    return """
# Blocage du robot d'entrainement d'IA de Meta
User-agent: meta-externalagent
User-agent: dotbot
User-agent: Bytespider
Disallow: /

User-agent: *
Allow: /
Sitemap: https://colibre.fr/sitemap.xml
"""


@app.server.route("/robots.txt")
def robots():
    return Response(_build_robots_txt(DEVELOPMENT), mimetype="text/plain")


# Index de sitemaps + sous-sitemaps paginés (voir src.utils.sitemap).
from src.utils import sitemap as _sitemap  # noqa: E402  # src.db doit être prêt


@app.server.route("/sitemap.xml")
def sitemap():
    return Response(_sitemap.build_index(), mimetype="application/xml")


@app.server.route("/sitemap-pages.xml")
def sitemap_pages():
    return Response(_sitemap.build_pages(), mimetype="application/xml")


@app.server.route("/sitemap-arbre.xml")
def sitemap_arbre():
    return Response(_sitemap.build_arbre(), mimetype="application/xml")


@app.server.route("/sitemap-<segment>-<int:page>.xml")
def sitemap_org(segment: str, page: int):
    xml = _sitemap.build_org_page(segment, page)
    if xml is None:
        return Response("Not found", status=404)
    return Response(xml, mimetype="application/xml")


@app.server.route("/llms.txt")
def llms():
    return redirect("/assets/llms.md")


# Fichier .ics d'une rencontre (voir src.rencontres). La route appelle
# openagenda.fetch_rencontres() via le module pour rester monkeypatchable.
from src.rencontres import openagenda as _openagenda  # noqa: E402
from src.rencontres.calendrier import ics_evenement as _ics_evenement  # noqa: E402


@app.server.route("/rencontres/<uid>.ics")
def rencontre_ics(uid: str):
    for ev in _openagenda.fetch_rencontres():
        if ev.uid == uid:
            return Response(
                _ics_evenement(ev),
                mimetype="text/calendar",
                headers={
                    "Content-Disposition": f'attachment; filename="rencontre-{uid}.ics"'
                },
            )
    return Response("Not found", status=404)


with open("./pyproject.toml", "rb") as f:
    pyproject = tomllib.load(f)
    version = "v" + pyproject["project"]["version"]

# Widget de chat Chatwoot (essai, issue #120) : chaîne vide si la variable
# d'env n'est pas définie, ce qui désactive le widget (utilisé notamment
# pour ne jamais le charger pendant les tests/CI).
chatwoot_script = build_widget_script(os.getenv("CHATWOOT_WEBSITE_TOKEN"))

app.index_string = """
<!DOCTYPE html>
<html lang="fr">
    <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="shortcut icon" href="/assets/icons/favicon.ico">
        <link rel="apple-touch-icon" sizes="180x180" href="/assets/icons/apple-touch-icon.png">
        <link rel="icon" type="image/png" sizes="32x32" href="/assets/icons/favicon-32x32.png">
        <link rel="icon" type="image/png" sizes="16x16" href="/assets/icons/favicon-16x16.png">
        <link rel="manifest" href="/assets/icons/site.webmanifest">
        {%css%}
        <!-- canonical auto-référent : l'index_string Dash est partagé par toutes
             les pages, donc on pose le href côté client d'après l'URL courante
             (sans query string). Google exécute le JS au rendu. -->
        <link rel="canonical" id="canonical-link">
        <script type="application/javascript">
            document.getElementById('canonical-link').setAttribute(
                'href', window.location.origin + window.location.pathname
            );
        </script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
        <script type="application/javascript">
            console.log("Matomo");
            var _paq = window._paq = window._paq || [];
            /* tracker methods like "setCustomDimension" should be called before "trackPageView" */
            _paq.push(['trackPageView']);
            _paq.push(['enableLinkTracking']);
            (function() {
                var u="//analytics.maudry.com/";
                _paq.push(['setTrackerUrl', u+'matomo.php']);
                _paq.push(['setSiteId', '14']);
                var d=document, g=d.createElement('script'), s=d.getElementsByTagName('script')[0];
                g.async=true; g.src=u+'matomo.js'; s.parentNode.insertBefore(g,s);
            })();
        </script>
        __CHATWOOT_SCRIPT__
    </body>
</html>
""".replace("__CHATWOOT_SCRIPT__", chatwoot_script)

# Dash génère automatiquement twitter:url par page (via register_page), mais pas
# og:url. On l'injecte ici à partir de l'URL de la requête en cours, pour que les
# crawlers sociaux (qui n'exécutent pas de JS, contrairement au canonical ci-dessus)
# reçoivent la bonne URL directement dans le HTML servi.
_default_interpolate_index = app.interpolate_index


def _interpolate_index_per_request(**kwargs):
    from flask import request as _request
    from markupsafe import escape as _escape

    og_url_tag = f'<meta property="og:url" content="{_escape(_request.url)}"/>'
    kwargs["metas"] = f"{kwargs.get('metas', '')}\n      {og_url_tag}"

    # Identité Chatwoot : le chargement du widget est figé dans index_string
    # (même token pour tout le monde), mais setUser dépend de la session, donc
    # il se pose ici, par requête. La connexion et la déconnexion passent par
    # des routes Flask avec redirection — donc par un vrai rechargement de page
    # —, ce qui suffit à resynchroniser l'identité malgré la navigation SPA.
    if chatwoot_script:
        if current_user.is_authenticated:
            identity = build_identity_script(
                current_user.id,
                current_user.email,
                os.getenv("CHATWOOT_HMAC_TOKEN"),
                custom_attributes=subscription_attributes(current_user.id),
            )
        elif _request.args.get("deconnexion") or _request.args.get("account_deleted"):
            identity = build_reset_script()
        else:
            identity = ""
        if identity:
            kwargs["scripts"] = f"{kwargs.get('scripts', '')}\n        {identity}"

    return _default_interpolate_index(**kwargs)


app.interpolate_index = _interpolate_index_per_request

navbar = dbc.Navbar(
    dbc.Container(
        fluid=True,
        children=[
            dbc.NavItem(
                children=[
                    html.Div(
                        [
                            dcc.Link(html.H1("colibre"), href="/", className="logo"),
                            html.P(
                                [
                                    html.A(
                                        version,
                                        href="/a-propos/roadmap",
                                    )
                                ],
                                className="version",
                            ),
                        ],
                        className="logo-wrapper",
                    )
                ],
                style={"minWidth": "230px"},
            ),
            dbc.Nav(
                children=[
                    dcc.Markdown(
                        os.getenv("ANNOUNCEMENTS"),
                        id="announcements",
                        dangerously_allow_html=True,
                    ),
                ],
                style={
                    "maxWidth": "1200px",
                    "display": "inline-block",
                },
                navbar=True,
                id="announcements-nav",
            ),
            dbc.NavbarToggler(id="navbar-toggler"),
            dbc.Collapse(
                dbc.Nav(
                    [
                        dbc.NavItem(
                            dbc.NavLink(
                                page["name"].replace(" ", " "),
                                href=page["relative_path"] + "/presentation"
                                if page["name"] == "À propos"
                                else page["relative_path"],
                                active="exact",
                            )
                        )
                        for page in page_registry.values()
                        if page["name"]
                        in ["Recherche", "À propos", "Tableau", "Observatoire"]
                    ]
                    + [html.Div(id="auth-nav-slot")],
                    className="ms-auto",
                    navbar=True,
                ),
                id="navbar-collapse",
                navbar=True,
            ),
        ],
    ),
    color="light",
    dark=False,
    className="mb-4",
    expand="lg",
)

app.layout = html.Div(
    [
        dcc.Store(id="csrf-token"),
        navbar,
        dbc.Container(
            page_container,
            fluid=True,
            id="page-content-container",
            className="mb-4",
        ),
    ]
)


@app.callback(
    Output("navbar-collapse", "is_open"),
    [Input("navbar-toggler", "n_clicks")],
    [State("navbar-collapse", "is_open")],
)
def toggle_navbar_collapse(n, is_open):
    if n:
        return not is_open
    return is_open


@callback(
    Output("auth-nav-slot", "children"),
    Input("auth-nav-slot", "id"),
)
def _auth_nav(_):
    if current_user.is_authenticated:
        # email = current_user.email
        # display = email if len(email) <= 30 else email[:27] + "..."
        display = "★★★"
        return dbc.NavItem(dbc.NavLink(display, href="/compte/admin"))
    return dbc.NavItem(dbc.NavLink("Connexion", href="/connexion"))


@callback(
    Output("csrf-token", "data"),
    Input("_pages_location", "pathname"),
    Input("auth-nav-slot", "children"),
)
def _generate_csrf_token(*_):
    from flask_wtf.csrf import generate_csrf

    return generate_csrf()


@callback(
    Output({"type": "csrf-input", "index": ALL}, "value"),
    Input("csrf-token", "data"),
)
def _fill_csrf_inputs(token):
    return [token] * len(ctx.outputs_list)


# Préchauffage du registre de ressources, à l'import donc AVANT que gunicorn ne
# serve la moindre requête.
#
# Dash ne remplit `app.registered_paths` (la liste blanche de /_dash-component-
# suites) que dans _generate_scripts_html, appelé par le before_request
# `_setup_server`. Or _setup_server pose son drapeau `_got_first_request` AVANT
# de faire le travail, et sans verrou : sur un worker gthread neuf, un 2e thread
# qui arrive pendant ce laps de temps saute l'initialisation et lit un registre
# à moitié construit. Le renderer demandant plotly.js à une URL codée en dur et
# sans empreinte (`_dash-component-suites/plotly/package_data/plotly.min.js`,
# cf. dash_renderer.min.js), la course se manifeste par des 500 « "plotly" is
# not a registered library » quelques secondes après chaque recyclage de worker
# (max_requests), comme observé sur test.colibre.fr du 23 au 29/07/2026.
#
# Ces deux méthodes sont idempotentes (rejouées à chaque rendu de page), donc
# les appeler ici ne fait qu'avancer le remplissage du registre.
app._generate_scripts_html()
app._generate_css_dist_html()
