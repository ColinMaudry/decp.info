import dash_bootstrap_components as dbc
from dash import html


def not_admin():
    return html.Div(
        html.H2("404", id="admin-404-heading"), className="py-5 text-center"
    )


def admin_nav(active: str):
    return dbc.Nav(
        [
            dbc.NavLink("Utilisateurs", href="/admin", active=(active == "liste")),
            dbc.NavLink("Journal", href="/admin/journal", active=(active == "journal")),
        ],
        pills=True,
        class_name="mb-4",
    )
