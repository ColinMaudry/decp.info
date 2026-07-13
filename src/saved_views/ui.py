import re

import dash_bootstrap_components as dbc
from dash import dcc, html
from unidecode import unidecode

from src.utils import DOMAIN_NAME


def controls_disabled(has_subscription: bool) -> bool:
    """Boutons « Sauvegarder la vue » / « Mes vues » : actifs pour les abonnés,
    grisés et désactivés sinon. La barre elle-même reste visible pour tous."""
    return not has_subscription


def clean_view_name(name: str | None) -> str:
    return (name or "").strip()


def slugify(name: str | None) -> str:
    """Slug décoratif en tirets (convention web) : minuscule, translittéré ASCII,
    non-alphanumériques → '-', collapse/trim. Ne contient jamais d'underscore
    (qui sert de séparateur slug↔jeton dans l'URL)."""
    ascii_name = unidecode(name or "").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")


def build_view_url(name: str, token: str) -> str:
    slug = slugify(name)
    prefix = f"{slug}_" if slug else ""
    return f"https://{DOMAIN_NAME}/tableau?vue={prefix}{token}"


def token_from_vue_param(value: str | None) -> str | None:
    """Extrait le jeton du paramètre ?vue=. Le jeton base62 ne contient pas d'`_`
    et le slug est en tirets, donc le segment après le dernier `_` est le jeton
    (`?vue=abc123` sans slug fonctionne aussi)."""
    if not value:
        return None
    token = value.rsplit("_", 1)[-1]
    return token or None


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
        dbc.DropdownMenuItem(
            view["name"],
            id={"type": "saved-view-item", "index": view["id"]},
            n_clicks=0,
        )
        for view in views
    ]


def _view_row(view) -> html.Div:
    view_id = view["id"]
    share_url = build_view_url(view["name"], view["token"])
    return html.Div(
        className="saved-view-row d-flex align-items-center gap-2 mb-2",
        children=[
            html.Span(view["name"], className="flex-grow-1"),
            dbc.Button(
                "Ouvrir",
                href=share_url,
                color="link",
                size="sm",
            ),
            dcc.Clipboard(
                content=share_url,
                title="Copier le lien vers cette vue",
                style={"cursor": "pointer", "fontSize": "1.1rem"},
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
