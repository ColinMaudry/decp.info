import pytest
from flask import Flask


@pytest.fixture
def mcp_app(monkeypatch, tmp_path):
    from src.api import tokens_db
    from src.auth import db as auth_db
    from src.mcp.auth import init_mcp_auth
    from src.subscriptions import db as sub_db

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    auth_db.reset_conn_for_tests()
    auth_db.init_schema()
    sub_db.init_schema()
    tokens_db.init_schema(db_path)

    app = Flask(__name__)

    @app.route("/_mcp", methods=["GET", "POST"])
    def _mcp():
        return "ok", 200

    init_mcp_auth(app)
    yield app, db_path
    auth_db.reset_conn_for_tests()


def _subscribed_uid():
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    uid = auth_db.create_user("mcp@ex.fr", "hash")
    _, sub_id = sub_db.create_pending(uid, "colibre-1", "simple")
    sub_db.set_status(sub_id, "active")
    return uid


def test_missing_header_401_with_challenge(mcp_app):
    app, _ = mcp_app
    resp = app.test_client().post("/_mcp")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == 'Bearer realm="colibre-mcp"'


def test_empty_bearer_401(mcp_app):
    app, _ = mcp_app
    resp = app.test_client().post("/_mcp", headers={"Authorization": "Bearer "})
    assert resp.status_code == 401


def test_unknown_token_401(mcp_app):
    app, _ = mcp_app
    resp = app.test_client().post(
        "/_mcp", headers={"Authorization": "Bearer colibre_unknown"}
    )
    assert resp.status_code == 401


def test_revoked_mcp_token_401(mcp_app):
    from src.api import tokens_db

    app, db_path = mcp_app
    uid = _subscribed_uid()
    token, tid = tokens_db.create_token(db_path, "x", user_id=uid, kind="mcp")
    tokens_db.revoke_user_token(db_path, tid, uid)
    resp = app.test_client().post("/_mcp", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_api_kind_token_rejected_401(mcp_app):
    from src.api import tokens_db

    app, db_path = mcp_app
    uid = _subscribed_uid()
    token, _ = tokens_db.create_token(db_path, "x", user_id=uid, kind="api")
    resp = app.test_client().post("/_mcp", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_mcp_token_without_user_403(mcp_app):
    from src.api import tokens_db

    app, db_path = mcp_app
    token, _ = tokens_db.create_token(db_path, "x", user_id=None, kind="mcp")
    resp = app.test_client().post("/_mcp", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_mcp_token_no_active_subscription_403(mcp_app):
    from src.api import tokens_db
    from src.auth import db as auth_db

    app, db_path = mcp_app
    uid = auth_db.create_user("nosub@ex.fr", "hash")  # aucun abonnement
    token, _ = tokens_db.create_token(db_path, "x", user_id=uid, kind="mcp")
    resp = app.test_client().post("/_mcp", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_mcp_token_active_subscription_passes_and_increments(mcp_app):
    from src.api import tokens_db

    app, db_path = mcp_app
    uid = _subscribed_uid()
    token, _ = tokens_db.create_token(db_path, "x", user_id=uid, kind="mcp")
    resp = app.test_client().post("/_mcp", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert tokens_db.get_token_by_plaintext(db_path, token)["count_total"] == 1


def test_tous_abonnes_bypasses_subscription(mcp_app, monkeypatch):
    from src.api import tokens_db
    from src.auth import db as auth_db

    monkeypatch.setattr("src.mcp.auth.TOUS_ABONNES", True)
    app, db_path = mcp_app
    uid = auth_db.create_user("nosub2@ex.fr", "hash")
    token, _ = tokens_db.create_token(db_path, "x", user_id=uid, kind="mcp")
    resp = app.test_client().post("/_mcp", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
