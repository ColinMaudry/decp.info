import dash_bootstrap_components as dbc
from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    ctx,
    html,
    no_update,
    register_page,
)
from flask_login import current_user

from src.pages._compte_shell import account_guard, account_shell
from src.saved_views import db as saved_views_db
from src.saved_views import ui as saved_views_ui

register_page(
    __name__,
    path="/compte/vues",
    title="Mes vues | colibre",
    name="Mes vues",
    description="Gérez vos vues enregistrées du tableau des marchés.",
)


def _content():
    views = saved_views_db.list_views(current_user.id, "tableau")
    return html.Div(
        [
            html.H2("Mes vues"),
            html.P(
                [
                    "Les vues que vous enregistrez depuis le Tableau apparaissent "
                    "ici. Cliquez sur ",
                    html.B("Ouvrir"),
                    " pour appliquer une vue, ou sur ",
                    html.B("Copier le lien"),
                    " pour copier son adresse Web et la partager par mail ou par message, y compris avec une personne qui n'a pas de compte colibre.",
                ]
            ),
            html.Div(saved_views_ui.views_table(views), id="vues-list"),
            dbc.Modal(
                id="vue-rename-modal",
                is_open=False,
                children=[
                    dbc.ModalHeader(dbc.ModalTitle("Renommer la vue")),
                    dbc.ModalBody(
                        dbc.Input(id="vue-rename-input", type="text", autofocus=True),
                    ),
                    dbc.ModalFooter(
                        dbc.Button("Renommer", id="vue-rename-confirm", color="primary")
                    ),
                ],
            ),
            dbc.Input(id="vue-rename-id", type="hidden"),
        ]
    )


def layout(**_):
    guard = account_guard("/compte/vues", require_subscription=True)
    if guard is not None:
        return guard
    return account_shell("vues", _content())


@callback(
    Output("vues-list", "children"),
    Input({"type": "vue-delete", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def delete_view(n_clicks):
    if not ctx.triggered_id or not any(n_clicks):
        return no_update
    saved_views_db.delete(ctx.triggered_id["index"], current_user.id)
    views = saved_views_db.list_views(current_user.id, "tableau")
    return saved_views_ui.views_table(views)


@callback(
    Output("vue-rename-modal", "is_open"),
    Output("vue-rename-id", "value"),
    Output("vue-rename-input", "value"),
    Input({"type": "vue-rename-open", "index": ALL}, "n_clicks"),
    Input("vue-rename-confirm", "n_clicks"),
    Input("vue-rename-input", "n_submit"),
    State("vue-rename-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_rename_modal(_open, _confirm, _submit, is_open):
    if isinstance(ctx.triggered_id, dict) and any(_open):
        view_id = ctx.triggered_id["index"]
        view = saved_views_db.get(view_id, current_user.id)
        return True, str(view_id), view["name"] if view else no_update
    return False, no_update, no_update


@callback(
    Output("vues-list", "children", allow_duplicate=True),
    Input("vue-rename-confirm", "n_clicks"),
    Input("vue-rename-input", "n_submit"),
    State("vue-rename-id", "value"),
    State("vue-rename-input", "value"),
    prevent_initial_call=True,
)
def rename_view(_n, _submit, view_id, new_name):
    clean = saved_views_ui.clean_view_name(new_name)
    if not view_id or not clean:
        return no_update
    try:
        saved_views_db.rename(int(view_id), current_user.id, clean)
    except Exception:
        return no_update
    views = saved_views_db.list_views(current_user.id, "tableau")
    return saved_views_ui.views_table(views)
