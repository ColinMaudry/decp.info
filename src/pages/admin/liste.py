import dash_bootstrap_components as dbc
from dash import dash_table, html, register_page

from src.admin.guard import is_admin
from src.auth.db import list_users
from src.pages.admin._shell import admin_nav, not_admin
from src.subscriptions.db import get_current

register_page(
    __name__,
    path="/admin",
    title="Panneau admin | colibre",
    name="Admin",
    description="Panneau d'administration interne.",
)


def _rows():
    rows = []
    for user in list_users():
        sub = get_current(user["id"])
        rows.append(
            {
                "email": user["email"],
                "vérifié": "oui" if user["email_verified"] else "non",
                "plan": sub["plan"] if sub else "",
                "statut": sub["status"] if sub else "",
                "créé le": user["created_at"],
                "voir": f"[Voir](/admin/user/{user['id']})",
            }
        )
    return rows


def layout(**_):
    if not is_admin():
        return not_admin()
    return dbc.Container(
        [
            html.H2("Panneau admin"),
            admin_nav("liste"),
            dash_table.DataTable(
                id="admin-users-table",
                columns=[
                    {"name": "Email", "id": "email"},
                    {"name": "Vérifié", "id": "vérifié"},
                    {"name": "Plan", "id": "plan"},
                    {"name": "Statut", "id": "statut"},
                    {"name": "Créé le", "id": "créé le"},
                    {"name": "", "id": "voir", "presentation": "markdown"},
                ],
                data=_rows(),
                filter_action="native",
                sort_action="native",
                page_action="native",
                page_size=20,
                markdown_options={"link_target": "_self"},
            ),
        ],
        fluid=True,
        className="py-4",
    )
