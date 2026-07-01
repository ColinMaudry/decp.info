import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html

SECTIONS = [
    {"key": "presentation", "label": "Présentation", "href": "/a-propos/presentation"},
    {"key": "explorer", "label": "Explorer le projet", "href": "/a-propos/explorer"},
    {"key": "donnees", "label": "Données", "href": "/a-propos/donnees"},
    # {"key": "contribuer", "label": "Contribuer", "href": "/a-propos/contribuer"},
    {
        "key": "abonnement",
        "label": "Abonnement",
        "href": "/a-propos/abonnement",
    },
    {
        "key": "roadmap",
        "label": "Roadmap",
        "href": "/a-propos/roadmap",
    },
    {"key": "contact", "label": "Contact", "href": "/a-propos/contact"},
    {
        "key": "mentions-legales",
        "label": "Mentions légales",
        "href": "/a-propos/mentions-legales",
    },
]


def _nav(active: str):
    links = [
        dbc.NavLink(s["label"], href=s["href"], active=(s["key"] == active))
        for s in SECTIONS
    ]
    return dbc.Nav(links, vertical=True, class_name="account-nav")


def apropos_shell(active: str, contenu):
    sidebar = dbc.Col(
        html.Div([html.H5("À propos", className="mb-3"), _nav(active)]),
        md=3,
        className="d-none d-md-block",
    )
    mobile = html.Div(
        [
            dbc.Button(
                "☰ Sections",
                id="apropos-offcanvas-open",
                color="secondary",
                outline=True,
                className="mb-3",
            ),
            dbc.Offcanvas(
                _nav(active),
                id="apropos-offcanvas",
                title="À propos",
                is_open=False,
            ),
        ],
        className="d-md-none",
    )
    content = dbc.Col([mobile, contenu], md=9)
    return dbc.Container(dbc.Row([sidebar, content]), className="py-4", fluid=True)


@callback(
    Output("apropos-offcanvas", "is_open"),
    Input("apropos-offcanvas-open", "n_clicks"),
    State("apropos-offcanvas", "is_open"),
    prevent_initial_call=True,
)
def _toggle_apropos_offcanvas(_n, is_open):
    return not is_open
