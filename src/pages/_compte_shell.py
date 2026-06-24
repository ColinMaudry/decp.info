import dash_bootstrap_components as dbc
from dash import dcc, html
from flask_login import current_user

# Définition centralisée des sections de l'espace compte.
# Ajouter une section future = ajouter une ligne ici (+ créer sa page).
SECTIONS = [
    {
        "key": "admin",
        "label": "Compte",
        "href": "/compte/admin",
        "require_subscription": False,
    },
    {
        "key": "abonnement",
        "label": "Abonnement",
        "href": "/compte/abonnement",
        "require_subscription": False,
    },
    {
        "key": "archives",
        "label": "Mes archives",
        "href": "/compte/archives",
        "require_subscription": True,
    },
    {
        "key": "filtres",
        "label": "Mes filtres",
        "href": "/compte/filtres",
        "require_subscription": True,
    },
    {
        "key": "siret",
        "label": "Mon SIRET",
        "href": "/compte/siret",
        "require_subscription": True,
    },
]


def current_user_has_subscription() -> bool:
    """Stub : à brancher sur la facturation (issue #73)."""
    return False


def visible_sections(has_subscription: bool) -> list[dict]:
    return [s for s in SECTIONS if has_subscription or not s["require_subscription"]]


def guard_redirect(
    is_authenticated: bool,
    has_subscription: bool,
    require_subscription: bool,
    path: str,
) -> str | None:
    if not is_authenticated:
        return f"/connexion?next={path}"
    if require_subscription and not has_subscription:
        return "/compte/abonnement"
    return None


def account_guard(path: str, require_subscription: bool):
    href = guard_redirect(
        current_user.is_authenticated,
        current_user_has_subscription(),
        require_subscription,
        path,
    )
    return dcc.Location(href=href, id="compte-guard-redirect") if href else None


def _nav(active: str):
    links = [
        dbc.NavLink(s["label"], href=s["href"], active=(s["key"] == active))
        for s in visible_sections(current_user_has_subscription())
    ]
    return dbc.Nav(links, vertical=True, pills=True)


def account_shell(active: str, contenu):
    sidebar = dbc.Col(
        html.Div([html.H5("Mon compte", className="mb-3"), _nav(active)]),
        md=3,
        className="d-none d-md-block",
    )
    mobile = html.Div(
        [
            dbc.Button(
                "☰ Sections",
                id="compte-offcanvas-open",
                color="secondary",
                outline=True,
                className="mb-3",
            ),
            dbc.Offcanvas(
                _nav(active),
                id="compte-offcanvas",
                title="Mon compte",
                is_open=False,
            ),
        ],
        className="d-md-none",
    )
    content = dbc.Col([mobile, contenu], md=9)
    return dbc.Container(dbc.Row([sidebar, content]), className="py-4")
