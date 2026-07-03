import dash_bootstrap_components as dbc
from dash import dash_table, html, register_page

from src.admin.db import list_actions
from src.admin.guard import is_admin
from src.pages.admin._shell import admin_nav, not_admin

register_page(
    __name__,
    path="/admin/journal",
    title="Journal admin | colibre",
    name="Journal admin",
    description="Panneau d'administration interne.",
)


def _rows():
    rows = []
    for action in list_actions():
        target = action["target_user_id"]
        rows.append(
            {
                "date": action["created_at"],
                "admin": action["admin_email"],
                "action": action["action"],
                "user": f"[{target}](/admin/user/{target})" if target else "",
                "détails": action["details"] or "",
            }
        )
    return rows


def layout(**_):
    if not is_admin():
        return not_admin()
    return dbc.Container(
        [
            html.H2("Journal des actions admin"),
            admin_nav("journal"),
            dash_table.DataTable(
                id="admin-journal-table",
                columns=[
                    {"name": "Date", "id": "date"},
                    {"name": "Admin", "id": "admin"},
                    {"name": "Action", "id": "action"},
                    {"name": "User", "id": "user", "presentation": "markdown"},
                    {"name": "Détails", "id": "détails"},
                ],
                data=_rows(),
                sort_action="native",
                page_action="native",
                page_size=20,
                markdown_options={"link_target": "_self"},
            ),
        ],
        fluid=True,
        className="py-4",
    )
