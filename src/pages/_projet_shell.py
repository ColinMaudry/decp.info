import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html

SECTIONS = [
    {"key": "presentation", "label": "Présentation", "href": "/projet/presentation"},
    {"key": "explorer", "label": "Explorer le projet", "href": "/projet/explorer"},
    {
        "key": "donnees",
        "label": "Données",
        "href": "/projet/donnees",
        # Sous-sections dépliées sous le lien quand la section est active :
        # la page est longue, les ancres évitent de la parcourir au jugé.
        "anchors": [
            ("donnees-brutes", "Consommer les données brutes"),
            ("qualite", "Qualité et exhaustivité"),
            ("champs", "Liste des champs"),
            ("sources", "Sources de données"),
        ],
    },
    # {"key": "contribuer", "label": "Contribuer", "href": "/projet/contribuer"},
    {
        "key": "abonnement",
        "label": "Abonnement",
        "href": "/projet/abonnement",
    },
    {
        "key": "roadmap",
        "label": "Roadmap",
        "href": "/projet/roadmap",
    },
    {"key": "contact", "label": "Contact", "href": "/projet/contact"},
    {
        "key": "mentions-legales",
        "label": "Mentions légales",
        "href": "/projet/mentions-legales",
    },
]


def _nav(active: str, anchors: bool = True):
    """Nav latérale des pages /projet.

    `anchors=False` pour le menu burger mobile : replié dans un offcanvas, il
    ne fait découvrir les sous-sections à personne, et cliquer l'une d'elles y
    défile derrière le panneau — que sa fermeture ramène ensuite en haut de
    page (Bootstrap restaure la position mémorisée à l'ouverture).
    """
    links = []
    for s in SECTIONS:
        is_active = s["key"] == active
        links.append(dbc.NavLink(s["label"], href=s["href"], active=is_active))
        if not is_active or not anchors:
            continue
        links.extend(
            # Le défilement vers l'ancre est fait par src/assets/anchors.js :
            # dcc.Link intercepte le clic côté client, donc le saut natif du
            # navigateur n'a pas lieu.
            dbc.NavLink(
                label,
                href=f"{s['href']}#{anchor}",
                class_name="projet-subnav-link",
            )
            for anchor, label in s.get("anchors", ())
        )
    return dbc.Nav(links, vertical=True, class_name="account-nav")


def projet_shell(active: str, contenu):
    sidebar = dbc.Col(
        # La classe collante est sur le bloc intérieur, pas sur la colonne :
        # dbc.Row étire ses colonnes sur toute la hauteur (flex), ce qui ne
        # laisse à un `position: sticky` posé sur la Col aucune marge de
        # défilement — il ne collerait jamais.
        html.Div(
            [html.H5("Le projet", className="mb-3"), _nav(active)],
            className="shell-nav-sticky",
        ),
        md=3,
        className="d-none d-md-block",
    )
    mobile = html.Div(
        [
            dbc.Button(
                "☰ Sections",
                id="projet-offcanvas-open",
                color="secondary",
                outline=True,
                className="mb-3",
            ),
            dbc.Offcanvas(
                _nav(active, anchors=False),
                id="projet-offcanvas",
                title="Le projet",
                is_open=False,
            ),
        ],
        className="d-md-none",
    )
    content = dbc.Col([mobile, contenu], md=9)
    return dbc.Container(dbc.Row([sidebar, content]), className="py-4", fluid=True)


@callback(
    Output("projet-offcanvas", "is_open"),
    Input("projet-offcanvas-open", "n_clicks"),
    State("projet-offcanvas", "is_open"),
    prevent_initial_call=True,
)
def _toggle_projet_offcanvas(_n, is_open):
    return not is_open
