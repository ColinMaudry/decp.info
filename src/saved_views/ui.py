import dash_bootstrap_components as dbc
from dash import html


def bar_style(has_subscription: bool) -> dict:
    return {} if has_subscription else {"display": "none"}


def clean_view_name(name: str | None) -> str:
    return (name or "").strip()


def prepare_view_to_save(
    has_subscription: bool, name: str | None
) -> tuple[str | None, str | None]:
    if not has_subscription:
        return None, "Réservé aux abonné·es."
    clean = clean_view_name(name)
    if not clean:
        return None, "Veuillez saisir un nom pour la vue."
    return clean, None


def saved_views_items(views) -> list:
    return [
        dbc.DropdownMenuItem(view["name"], href=f"/tableau?{view['query']}")
        for view in views
    ]


def _view_row(view) -> html.Div:
    view_id = view["id"]
    return html.Div(
        className="saved-view-row d-flex align-items-center gap-2 mb-2",
        children=[
            html.Span(view["name"], className="flex-grow-1"),
            dbc.Button(
                "Ouvrir",
                href=f"/tableau?{view['query']}",
                color="link",
                size="sm",
            ),
            dbc.Button(
                "Renommer",
                id={"type": "vue-rename-open", "index": view_id},
                color="secondary",
                outline=True,
                size="sm",
            ),
            dbc.Button(
                "Supprimer",
                id={"type": "vue-delete", "index": view_id},
                color="danger",
                outline=True,
                size="sm",
            ),
        ],
    )


def views_table(views) -> html.Div:
    if not views:
        return html.Div(
            html.P(
                "Vous n'avez pas encore de vue enregistrée. "
                "Créez-en une depuis le Tableau, bouton « Sauvegarder la vue »."
            )
        )
    return html.Div([_view_row(v) for v in views])
