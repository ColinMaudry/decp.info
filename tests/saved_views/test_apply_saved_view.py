"""Régression revue finale #41 : apply_saved_view (callback qui RAPPELLE une vue
sauvegardée) ne doit pas planter si row["query"] est encore au format
pré-migration (query string, ex. "filtres=a&tris=b"), stocké par l'ancienne
build_view_query avant que Task 10 ne migre save_view vers du JSON
{"filterModel": ..., "columnState": ...}.
"""

from unittest.mock import patch

import dash

import src.app  # noqa: F401  # instancie l'app → register_page() des pages
from src.auth import db as auth_db
from src.pages import tableau
from src.saved_views import db as saved_views_db


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
        filter_model, column_state = tableau.apply_saved_view(
            [1], [{"type": "saved-view-item", "index": view_id}]
        )

    assert filter_model is dash.no_update
    assert column_state is dash.no_update


def test_apply_saved_view_new_format_returns_view(monkeypatch, users_db_path):
    saved_views_db.init_schema()
    uid = _make_user()
    query = (
        '{"filterModel": {"objet": {"filterType": "text", "filter": "route"}}, '
        '"columnState": [{"colId": "montant", "sort": "desc"}]}'
    )
    saved_views_db.upsert(uid, "tableau", "Vue récente", query)
    view_id = saved_views_db.list_views(uid, "tableau")[0]["id"]

    _Ctx.triggered_id = {"type": "saved-view-item", "index": view_id}
    monkeypatch.setattr(tableau, "ctx", _Ctx)

    with patch.object(tableau, "current_user", _fake_user(uid)):
        filter_model, column_state = tableau.apply_saved_view(
            [1], [{"type": "saved-view-item", "index": view_id}]
        )

    assert filter_model == {"objet": {"filterType": "text", "filter": "route"}}
    assert column_state == [{"colId": "montant", "sort": "desc"}]
