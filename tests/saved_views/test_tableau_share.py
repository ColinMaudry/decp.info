import json

import dash

import src.app  # noqa: F401  # instancie l'app → register_page()
from src.auth import db as auth_db
from src.pages import tableau
from src.saved_views import db as saved_views_db
from src.saved_views import resolve
from src.utils.query_ast import And, Condition, ast_to_dict


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def _seed(uid, name="Ma vue"):
    ast = And([Condition("objet", "contains", "route")])
    query = json.dumps(
        {"ast": ast_to_dict(ast), "columnState": [{"colId": "montant", "hide": True}]}
    )
    return saved_views_db.upsert(uid, "tableau", name, query)


def test_resolve_vue_from_url_found(monkeypatch, users_db_path):
    monkeypatch.setattr(resolve.ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed(uid)
    out = tableau.resolve_vue_from_url(f"?vue=ma-vue_{token}")
    assert out["found"] is True
    assert out["token"] == token


def test_resolve_vue_from_url_no_param_returns_none(users_db_path):
    saved_views_db.init_schema()
    assert tableau.resolve_vue_from_url("") is None
    assert tableau.resolve_vue_from_url("?autre=1") is None


def test_apply_vue_resolution_found_shows_box(users_db_path):
    resolution = {
        "found": True,
        "filter_model": {
            "objet": {"filterType": "text", "type": "contains", "filter": "route"}
        },
        "column_state": [{"colId": "montant", "hide": True}],
        "hidden_columns": ["montant"],
        "token": "abc123",
        "url": "https://test.colibre.fr/tableau?vue=ma-vue_abc123",
        "error": None,
    }
    fm, cs, hidden, active, suppress, feedback = tableau.apply_vue_resolution(
        resolution
    )
    assert fm == resolution["filter_model"]
    assert cs == resolution["column_state"]
    assert hidden == ["montant"]
    assert active == {"token": "abc123", "url": resolution["url"]}
    assert suppress == 1
    assert feedback == ""


def test_apply_vue_resolution_not_found_shows_alert(users_db_path):
    resolution = {
        "found": False,
        "filter_model": None,
        "column_state": None,
        "hidden_columns": None,
        "token": None,
        "url": None,
        "error": resolve.NOT_FOUND_MESSAGE,
    }
    fm, cs, hidden, active, suppress, feedback = tableau.apply_vue_resolution(
        resolution
    )
    assert fm is dash.no_update
    assert cs is dash.no_update
    assert active is None
    assert suppress == 0
    assert resolve.NOT_FOUND_MESSAGE in str(feedback)


def test_apply_vue_resolution_none_is_noop(users_db_path):
    out = tableau.apply_vue_resolution(None)
    assert all(v is dash.no_update for v in out)
