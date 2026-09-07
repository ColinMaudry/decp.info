import dash_bootstrap_components as dbc
from dash import (
    Input,
    Output,
    State,
    callback,
    ctx,
    dash_table,
    html,
    no_update,
    register_page,
)
from dash.exceptions import PreventUpdate
from flask_login import current_user

from src.admin.db import log_action
from src.admin.guard import is_admin
from src.admin.tables import all_tables, find_changed_cell, get_rows, set_cell
from src.pages.admin._shell import not_admin

register_page(
    __name__,
    path="/admin",
    title="Panneau admin | colibre",
    name="Admin",
    description="Panneau d'administration interne.",
)

DEFAULT_TABLE = "users"


def _columns_for(table: str):
    cfg = all_tables()[table]
    return [
        {
            "name": col,
            "id": col,
            "editable": col in cfg.editable_columns,
            **({"presentation": "dropdown"} if col in cfg.dropdowns else {}),
        }
        for col in cfg.columns
    ]


def _dropdown_for(table: str):
    cfg = all_tables()[table]
    return {
        col: {"options": [{"label": v, "value": v} for v in values]}
        for col, values in cfg.dropdowns.items()
    }


def layout(**_):
    if not is_admin():
        return not_admin()
    return dbc.Container(
        [
            html.H2("Panneau admin"),
            html.Div(id="admin-alerts"),
            dbc.Select(
                id="admin-table-select",
                options=[{"label": name, "value": name} for name in all_tables()],
                value=DEFAULT_TABLE,
                className="mb-3",
                style={"maxWidth": "300px"},
            ),
            dash_table.DataTable(
                id="admin-table",
                columns=_columns_for(DEFAULT_TABLE),
                data=get_rows(DEFAULT_TABLE),
                dropdown=_dropdown_for(DEFAULT_TABLE),
                editable=True,
                filter_action="native",
                sort_action="native",
                page_action="native",
                page_size=20,
            ),
        ],
        fluid=True,
        className="py-4",
    )


@callback(
    Output("admin-table", "data"),
    Output("admin-table", "columns"),
    Output("admin-table", "dropdown"),
    Output("admin-alerts", "children"),
    Input("admin-table-select", "value"),
    Input("admin-table", "data"),
    State("admin-table", "data_previous"),
    prevent_initial_call=True,
)
def _update_table(selected_table, data, data_previous):
    # Les callbacks Dash sont des endpoints serveur globaux (/_dash-update-component)
    # invocables indépendamment du layout rendu : la garde is_admin() de layout()
    # ne protège QUE l'affichage. Sans ce contrôle, n'importe qui (y compris un
    # anonyme) pourrait lire/écrire toute la base via ce callback. Voir issue #110.
    if not is_admin():
        raise PreventUpdate

    if ctx.triggered_id == "admin-table-select":
        return (
            get_rows(selected_table),
            _columns_for(selected_table),
            _dropdown_for(selected_table),
            None,
        )

    change = find_changed_cell(data, data_previous)
    if change is None:
        return no_update, no_update, no_update, None

    row_index, column, old_value, new_value = change
    cfg = all_tables()[selected_table]
    pk_value = data[row_index][cfg.pk]
    try:
        set_cell(selected_table, pk_value, column, new_value)
    except ValueError as exc:
        return (
            no_update,
            no_update,
            no_update,
            dbc.Alert(str(exc), color="danger", dismissable=True),
        )

    target_user_id = cfg.target_user_id(data[row_index])
    log_action(
        current_user.email,
        f"edit_{selected_table}",
        target_user_id,
        f"{column}: {old_value!r} → {new_value!r}",
    )
    return (
        no_update,
        no_update,
        no_update,
        dbc.Alert("Modification enregistrée.", color="success", dismissable=True),
    )
