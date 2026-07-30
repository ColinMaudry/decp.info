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
    from src.mcp import usage
    from src.mcp.oauth import store as oauth_store

    auth_db.reset_conn_for_tests()
    auth_db.init_schema()
    sub_db.init_schema()
    tokens_db.init_schema(db_path)
    oauth_store.init_schema(db_path)
    usage.init_schema(db_path)

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
    assert resp.headers["WWW-Authenticate"].startswith('Bearer realm="colibre-mcp"')


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


def test_mcp_get_authenticates_but_does_not_increment_usage(mcp_app):
    import sqlite3

    from src.api import tokens_db

    app, db_path = mcp_app
    uid = _subscribed_uid()
    token, _ = tokens_db.create_token(db_path, "x", user_id=uid, kind="mcp")
    resp = app.test_client().get("/_mcp", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert tokens_db.get_token_by_plaintext(db_path, token)["count_total"] == 0

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM mcp_usage").fetchone()[0] == 0
    finally:
        conn.close()


def test_tous_abonnes_bypasses_subscription(mcp_app, monkeypatch):
    from src.api import tokens_db
    from src.auth import db as auth_db

    monkeypatch.setattr("src.mcp.auth.TOUS_ABONNES", True)
    app, db_path = mcp_app
    uid = auth_db.create_user("nosub2@ex.fr", "hash")
    token, _ = tokens_db.create_token(db_path, "x", user_id=uid, kind="mcp")
    resp = app.test_client().post("/_mcp", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_oauth_token_active_subscription_passes(mcp_app, monkeypatch):
    import time

    from src.mcp.oauth import server, store

    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    app, db_path = mcp_app
    store.init_schema(db_path)
    uid = _subscribed_uid()
    store.create_client(db_path, "cid", {"redirect_uris": []})
    store.save_token(
        db_path,
        access_token="opaque123",
        refresh_token=None,
        client_id="cid",
        user_id=uid,
        scope="mcp",
        resource="https://colibre.fr/_mcp",
        access_expires_at=server._iso(time.time() + 3600),
        refresh_expires_at=None,
    )
    resp = app.test_client().post(
        "/_mcp", headers={"Authorization": "Bearer opaque123"}
    )
    assert resp.status_code == 200


def test_oauth_token_wrong_audience_401(mcp_app, monkeypatch):
    import time

    from src.mcp.oauth import server, store

    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    app, db_path = mcp_app
    store.init_schema(db_path)
    uid = _subscribed_uid()
    store.save_token(
        db_path,
        access_token="badaud",
        refresh_token=None,
        client_id="cid",
        user_id=uid,
        scope="mcp",
        resource="https://evil.example/_mcp",
        access_expires_at=server._iso(time.time() + 3600),
        refresh_expires_at=None,
    )
    resp = app.test_client().post("/_mcp", headers={"Authorization": "Bearer badaud"})
    assert resp.status_code == 401


def test_401_carries_resource_metadata(mcp_app, monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    app, _ = mcp_app
    resp = app.test_client().post("/_mcp")
    assert resp.status_code == 401
    assert "resource_metadata=" in resp.headers["WWW-Authenticate"]


def test_oauth_token_no_subscription_403(mcp_app, monkeypatch):
    import time

    from src.auth import db as auth_db
    from src.mcp.oauth import server, store

    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    monkeypatch.setattr("src.mcp.auth.TOUS_ABONNES", False)
    app, db_path = mcp_app
    store.init_schema(db_path)
    uid = auth_db.create_user("nosuboauth@ex.fr", "h")  # aucun abonnement
    store.save_token(
        db_path,
        access_token="nosubtok",
        refresh_token=None,
        client_id="cid",
        user_id=uid,
        scope="mcp",
        resource="https://colibre.fr/_mcp",
        access_expires_at=server._iso(time.time() + 3600),
        refresh_expires_at=None,
    )
    resp = app.test_client().post("/_mcp", headers={"Authorization": "Bearer nosubtok"})
    assert resp.status_code == 403
