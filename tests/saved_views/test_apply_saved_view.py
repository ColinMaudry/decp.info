"""Régression revue finale #41 : apply_saved_view (callback qui RAPPELLE une vue
sauvegardée) ne doit pas planter si row["query"] est encore au format
pré-migration (query string, ex. "filtres=a&tris=b"), stocké par l'ancienne
build_view_query avant que Task 10 ne migre save_view vers du JSON.

Depuis le round 2 de la revue finale, le format JSON stocké est
{"ast": ..., "columnState": ...} (AST canonique, indépendant de l'UI) plutôt
que {"filterModel": ..., "columnState": ...} (filterModel brut d'AG Grid) :
cf. spec de conception. apply_saved_view doit aussi resynchroniser
tableau-hidden-columns à partir du columnState rappelé.
"""

import json
from unittest.mock import patch

import dash

import src.app  # noqa: F401  # instancie l'app → register_page() des pages
from src.auth import db as auth_db
from src.pages import tableau
from src.saved_views import db as saved_views_db
from src.utils.query_ast import And, Condition, ast_to_dict


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def _fake_user(user_id, authenticated=True):
    user = type("U", (), {})()
    user.is_authenticated = authenticated
    user.id = user_id
    return user


class _Ctx:
    triggered_id = None


def test_apply_saved_view_old_format_returns_no_update(monkeypatch, users_db_path):
    saved_views_db.init_schema()
    uid = _make_user()
    saved_views_db.upsert(uid, "tableau", "Vue historique", "filtres=a&tris=b")
    view_id = saved_views_db.list_views(uid, "tableau")[0]["id"]

    _Ctx.triggered_id = {"type": "saved-view-item", "index": view_id}
    monkeypatch.setattr(tableau, "ctx", _Ctx)

    with patch.object(tableau, "current_user", _fake_user(uid)):
        filter_model, column_state, hidden_columns, active = tableau.apply_saved_view(
            [1], [{"type": "saved-view-item", "index": view_id}]
        )

    assert filter_model is dash.no_update
    assert column_state is dash.no_update
    assert hidden_columns is dash.no_update
    assert active is dash.no_update


def test_apply_saved_view_new_format_returns_view(monkeypatch, users_db_path):
    """row["query"] au format post-round-2 : {"ast": ..., "columnState": ...},
    AST canonique plutôt que filterModel brut d'AG Grid."""
    saved_views_db.init_schema()
    uid = _make_user()
    ast = And([Condition("objet", "contains", "route")])
    column_state = [
        {"colId": "montant", "sort": "desc"},
        {"colId": "acheteur_nom", "hide": True},
    ]
    query = json.dumps({"ast": ast_to_dict(ast), "columnState": column_state})
    saved_views_db.upsert(uid, "tableau", "Vue récente", query)
    view_id = saved_views_db.list_views(uid, "tableau")[0]["id"]

    _Ctx.triggered_id = {"type": "saved-view-item", "index": view_id}
    monkeypatch.setattr(tableau, "ctx", _Ctx)

    with patch.object(tableau, "current_user", _fake_user(uid)):
        filter_model, returned_column_state, hidden_columns, active = (
            tableau.apply_saved_view(
                [1], [{"type": "saved-view-item", "index": view_id}]
            )
        )

    assert filter_model == {
        "objet": {"filterType": "text", "type": "contains", "filter": "route"}
    }
    assert returned_column_state == column_state
    # tableau-hidden-columns doit être resynchronisé à partir du columnState
    # rappelé (revue finale #41, round 2) : seules les colonnes avec hide=True.
    assert hidden_columns == ["acheteur_nom"]
    # active-view alimente le bloc de partage (token + URL courte).
    assert active["token"] and active["url"].endswith(f"_{active['token']}")


def test_apply_saved_view_missing_ast_key_degrades_gracefully(
    monkeypatch, users_db_path
):
    """Vue stockée dans un format intermédiaire (sans clé "ast", ex. l'ancien
    format {"filterModel": ..., "columnState": ...} produit avant le round 2) :
    ast_from_dict(None) -> None, ast_to_filtermodel(None, schema) -> {} — la
    vue se rappelle sans filtre plutôt que de planter le callback."""
    saved_views_db.init_schema()
    uid = _make_user()
    column_state = [{"colId": "montant", "sort": "desc"}]
    query = json.dumps(
        {
            "filterModel": {"objet": {"filterType": "text", "filter": "route"}},
            "columnState": column_state,
        }
    )
    saved_views_db.upsert(uid, "tableau", "Vue ancien format", query)
    view_id = saved_views_db.list_views(uid, "tableau")[0]["id"]

    _Ctx.triggered_id = {"type": "saved-view-item", "index": view_id}
    monkeypatch.setattr(tableau, "ctx", _Ctx)

    with patch.object(tableau, "current_user", _fake_user(uid)):
        filter_model, returned_column_state, hidden_columns, _active = (
            tableau.apply_saved_view(
                [1], [{"type": "saved-view-item", "index": view_id}]
            )
        )

    assert filter_model == {}
    assert returned_column_state == column_state
    assert hidden_columns == []
