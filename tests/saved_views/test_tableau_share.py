import json
from unittest.mock import patch

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


def _fake_user(user_id):
    u = type("U", (), {})()
    u.is_authenticated = True
    u.id = user_id
    return u


class _Ctx:
    triggered_id = None


def test_render_share_box_visible_when_active():
    style, value = tableau.render_share_box(
        {"token": "abc123", "url": "https://x/tableau?vue=a_abc123"}
    )
    assert style == {}
    assert value == "https://x/tableau?vue=a_abc123"


def test_render_share_box_hidden_when_none():
    style, value = tableau.render_share_box(None)
    assert style == {"display": "none"}
    assert value == ""


def test_hide_lock_consumes_echo_then_hides():
    # 1er changement = écho de l'application (suppress=1) → garde la box.
    active, suppress = tableau.hide_share_box_on_change({}, [], 1)
    assert active is dash.no_update
    assert suppress == 0
    # Changement réel suivant (suppress=0) → masque.
    active2, suppress2 = tableau.hide_share_box_on_change({"objet": {}}, [], 0)
    assert active2 is None
    assert suppress2 == 0


def test_apply_saved_view_sets_active_and_suppress(monkeypatch, users_db_path):
    monkeypatch.setattr(tableau.saved_views_ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed(uid, "Ma vue")
    view_id = saved_views_db.list_views(uid, "tableau")[0]["id"]
    _Ctx.triggered_id = {"type": "saved-view-item", "index": view_id}
    monkeypatch.setattr(tableau, "ctx", _Ctx)
    with patch.object(tableau, "current_user", _fake_user(uid)):
        out = tableau.apply_saved_view(
            [1], [{"type": "saved-view-item", "index": view_id}]
        )
    # (filter_model, column_state, hidden, active-view, suppress-next)
    assert out[3] == {
        "token": token,
        "url": f"https://test.colibre.fr/tableau?vue=ma-vue_{token}",
    }
    assert out[4] == 1


def test_save_view_shows_box(monkeypatch, users_db_path):
    monkeypatch.setattr(tableau.saved_views_ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    monkeypatch.setattr(tableau, "current_user_has_subscription", lambda: True)
    with patch.object(tableau, "current_user", _fake_user(uid)):
        out = tableau.save_view(1, "Nouvelle", {}, [])
    # (is_open, feedback, refresh, active-view, suppress-next)
    assert out[3]["url"].startswith("https://test.colibre.fr/tableau?vue=nouvelle_")
    assert out[4] == 0  # sauvegarde ne modifie pas la grille → pas d'écho
