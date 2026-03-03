import logging
import os

import dash_bootstrap_components as dbc
import tomllib
from dash import Dash, Input, Output, State, dcc, html, page_container, page_registry
from dotenv import load_dotenv
from flask import Response

load_dotenv()

# if os.getenv("PYTEST_CURRENT_TEST"):
#     os.environ["DATA_FILE_PARQUET_PATH"]


development = os.getenv("DEVELOPMENT").lower() == "true"

meta_tags = [
    {"name": "viewport", "content": "width=device-width, initial-scale=1"},
    {
        "name": "keywords",
        "content": "commande publique, decp, marchés publics, données essentielles",
    },
]

if development:
    meta_tags.append({"name": "robots", "content": "noindex"})

app: Dash = Dash(
    title="decp.info",
    use_pages=True,
    compress=True,
    meta_tags=meta_tags,
)

# COSMO (belle font, blue),
# UNITED (rouge, ubuntu font),
# LUMEN (gros séparateur, blue clair),
# SIMPLEX (rouge, séparateur)


# robots.txt
@app.server.route("/robots.txt")
def robots():
    text = """User-agent: *
Allow: /
    """
    return Response(text, mimetype="text/plain")


@app.server.route("/sitemap.xml")
def sitemap():
    base_url = "https://decp.info"
    pages = [
        "/",
        "/statistiques",
        "/tableau",
        "/a-propos",
    ]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for page in pages:
        xml += "  <url>\n"
        xml += f"    <loc>{base_url}{page}</loc>\n"
        xml += "  </url>\n"
    xml += "</urlset>"
    return Response(xml, mimetype="text/xml")


logger = logging.getLogger("decp.info")
logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

with open("./pyproject.toml", "rb") as f:
    pyproject = tomllib.load(f)
    version = "v" + pyproject["project"]["version"]


app.index_string = """
<!DOCTYPE html>
<html lang="fr">
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <!-- canonical link -->
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
    </body>
</html>
"""

navbar = dbc.Navbar(
    dbc.Container(
        fluid=True,
        children=[
            dbc.NavItem(
                children=[
                    html.Div(
                        [
                            dcc.Link(html.H1("decp.info"), href="/", className="logo"),
                            html.P(
                                [
                                    html.A(
                                        version,
                                        href="https://github.com/ColinMaudry/decp.info/blob/main/CHANGELOG.md",
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
                children=[dcc.Markdown(os.getenv("ANNOUNCEMENTS"), id="announcements")],
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
                                href=page["relative_path"],
                                active="exact",
                            )
                        )
                        for page in page_registry.values()
                        if page["name"]
                        in ["Recherche", "À propos", "Tableau", "Statistiques"]
                    ],
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
