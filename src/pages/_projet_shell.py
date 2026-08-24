import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html

SECTIONS = [
    {"key": "presentation", "label": "Présentation", "href": "/projet/presentation"},
    {"key": "explorer", "label": "Explorer le projet", "href": "/projet/explorer"},
    {"key": "donnees", "label": "Données", "href": "/projet/donnees"},
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


def _nav(active: str):
    links = [
        dbc.NavLink(s["label"], href=s["href"], active=(s["key"] == active))
        for s in SECTIONS
    ]
    return dbc.Nav(links, vertical=True, class_name="account-nav")


def projet_shell(active: str, contenu):
    sidebar = dbc.Col(
        html.Div([html.H5("Le projet", className="mb-3"), _nav(active)]),
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
                _nav(active),
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
