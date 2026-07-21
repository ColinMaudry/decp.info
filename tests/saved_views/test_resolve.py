import json

from src.auth import db as auth_db
from src.db import schema
from src.saved_views import db as saved_views_db
from src.saved_views import resolve
from src.utils.query_ast import And, Condition, ast_to_dict


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def _seed_view(uid, name="Ma vue"):
    ast = And([Condition("objet", "contains", "route")])
    column_state = [
        {"colId": "montant", "sort": "desc"},
        {"colId": "acheteur_nom", "hide": True},
    ]
    query = json.dumps({"ast": ast_to_dict(ast), "columnState": column_state})
    return saved_views_db.upsert(uid, "tableau", name, query)


def test_resolve_found_applies_view(monkeypatch, users_db_path):
    monkeypatch.setattr(resolve.ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed_view(uid, "Mes Marchés")

    out = resolve.resolve_vue_param(f"{token}_mes-marches", schema)

    assert out["found"] is True
    assert out["filter_model"] == {
        "objet": {"filterType": "text", "type": "contains", "filter": "route"}
    }
    assert out["hidden_columns"] == ["acheteur_nom"]
    assert out["token"] == token
    assert out["url"] == f"https://test.colibre.fr/tableau?vue={token}_mes-marches"
    assert out["error"] is None


def test_resolve_slug_is_ignored(monkeypatch, users_db_path):
    monkeypatch.setattr(resolve.ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed_view(uid)
    # Slug bidon → même résolution.
    out = resolve.resolve_vue_param(f"{token}_nimportequoi", schema)
    assert out["found"] is True
    assert out["token"] == token


def test_resolve_unknown_token_returns_error(users_db_path):
    saved_views_db.init_schema()
    _make_user()
    out = resolve.resolve_vue_param("zzzzzz_slug", schema)
    assert out["found"] is False
    assert out["error"] == resolve.NOT_FOUND_MESSAGE
    assert out["filter_model"] is None


def test_resolve_empty_param_returns_error(users_db_path):
    saved_views_db.init_schema()
    out = resolve.resolve_vue_param("", schema)
    assert out["found"] is False
    assert out["error"] == resolve.NOT_FOUND_MESSAGE


def test_resolve_corrupt_query_returns_error(users_db_path):
    saved_views_db.init_schema()
    uid = _make_user()
    # query pré-migration (pas du JSON) → même message de repli.
    token = saved_views_db.upsert(uid, "tableau", "Vieille", "filtres=a&tris=b")
    out = resolve.resolve_vue_param(f"{token}_vieille", schema)
    assert out["found"] is False
    assert out["error"] == resolve.NOT_FOUND_MESSAGE
