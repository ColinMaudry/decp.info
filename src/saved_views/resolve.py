"""Résolution publique d'une vue depuis le paramètre d'URL ?vue=<token>_<slug>.

Fonction pure (aucune dépendance à Dash), testable directement : elle prend le
paramètre brut et le schéma, renvoie un dict décrivant la vue à appliquer ou une
erreur. Le slug est ignoré ; seul le jeton fait foi.
"""

import json

from src.saved_views import db, ui
from src.utils import logger
from src.utils.query_ast import ast_from_dict, ast_to_filtermodel

NOT_FOUND_MESSAGE = "Cette vue est introuvable ou a été supprimée."


def _error() -> dict:
    return {
        "found": False,
        "filter_model": None,
        "column_state": None,
        "hidden_columns": None,
        "token": None,
        "url": None,
        "error": NOT_FOUND_MESSAGE,
    }


def resolve_vue_param(vue_param: str | None, schema) -> dict:
    token = ui.token_from_vue_param(vue_param)
    if not token:
        return _error()
    row = db.get_by_token(token)
    if row is None:
        return _error()
    try:
        view = json.loads(row["query"])
        # AST canonique stocké par save_view (cf. spec vues sauvegardées).
        ast = ast_from_dict(view.get("ast"))
        filter_model = ast_to_filtermodel(ast, schema)
        column_state = view.get("columnState") or []
    except (json.JSONDecodeError, TypeError, AttributeError):
        # Vue pré-migration (query string, pas du JSON) : repli propre, même
        # message que pour un jeton inconnu (anti-énumération).
        logger.warning(
            "Vue partagée au format pré-migration, non applicable : "
            f"token={token!r} name={row['name']!r}"
        )
        return _error()
    hidden_columns = [c["colId"] for c in column_state if c.get("hide")]
    return {
        "found": True,
        "filter_model": filter_model,
        "column_state": column_state,
        "hidden_columns": hidden_columns,
        "token": row["token"],
        "url": ui.build_view_url(row["name"], row["token"]),
        "error": None,
    }
