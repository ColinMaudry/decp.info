import base64
import hashlib
import re

import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin, login_user


class _U(UserMixin):
    def __init__(self, uid):
        self.id = uid


def _pkce():
    verifier = "a" * 64
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


@pytest.fixture
def flow_app(monkeypatch, tmp_path):
    from src.auth import db as auth_db
    from src.mcp.oauth import routes, store
    from src.subscriptions import db as sub_db

    db_path = tmp_path / "u.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    auth_db.reset_conn_for_tests()
    auth_db.init_schema()
    sub_db.init_schema()
    store.init_schema(db_path)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "x"
    app.config["SERVER_NAME"] = "colibre.fr"
    lm = LoginManager()
    lm.init_app(app)
    lm.user_loader(lambda uid: _U(int(uid)))
    routes.init_oauth(app)

    @app.route("/_test_login/<int:uid>")
    def _test_login(uid):
        login_user(_U(uid))
        return "ok"

    yield app, db_path
    auth_db.reset_conn_for_tests()


def _register(client):
    resp = client.post(
        "/oauth/register",
        json={
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "client_name": "Claude",
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "scope": "mcp offline_access",
        },
    )
    return resp.get_json()["client_id"]


def test_authorize_requires_subscription(flow_app, monkeypatch):
    from src.auth import db as auth_db

    app, _ = flow_app
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    uid = auth_db.create_user("nosub@ex.fr", "h")
    client = app.test_client()
    client.get(f"/_test_login/{uid}")
    cid = _register(client)
    _, challenge = _pkce()
    resp = client.get(
        "/oauth/authorize",
        query_string={
            "client_id": cid,
            "response_type": "code",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "scope": "mcp",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": "https://colibre.fr/_mcp",
        },
    )
    assert b"Abonnement requis" in resp.data


def test_authorize_post_requires_subscription(flow_app, monkeypatch):
    from src.auth import db as auth_db

    app, _ = flow_app
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    uid = auth_db.create_user("nosub2@ex.fr", "h")
    client = app.test_client()
    client.get(f"/_test_login/{uid}")
    cid = _register(client)
    _, challenge = _pkce()
    qs = {
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        "scope": "mcp",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": "https://colibre.fr/_mcp",
    }
    resp = client.post("/oauth/authorize", query_string=qs, data={"confirm": "yes"})
    assert resp.status_code == 403
    assert b"Abonnement requis" in resp.data


def test_full_flow_issues_audience_bound_token(flow_app, monkeypatch):
    from src.auth import db as auth_db
    from src.mcp.oauth import store
    from src.subscriptions import db as sub_db

    app, db_path = flow_app
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    uid = auth_db.create_user("sub@ex.fr", "h")
    _, sub_id = sub_db.create_pending(uid, "colibre-1", "simple")
    sub_db.set_status(sub_id, "active")

    client = app.test_client()
    client.get(f"/_test_login/{uid}")
    cid = _register(client)
    verifier, challenge = _pkce()
    qs = {
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        "scope": "mcp",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": "https://colibre.fr/_mcp",
    }
    # GET affiche le consentement
    assert b"Autoriser" in client.get("/oauth/authorize", query_string=qs).data
    # POST confirme → redirection avec ?code=
    resp = client.post("/oauth/authorize", query_string=qs, data={"confirm": "yes"})
    assert resp.status_code == 302
    code = re.search(r"code=([^&]+)", resp.headers["Location"]).group(1)
    # échange du code
    tok = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": cid,
            "code_verifier": verifier,
            "resource": "https://colibre.fr/_mcp",
        },
    )
    assert tok.status_code == 200
    access = tok.get_json()["access_token"]
    row = store.get_token_by_access(db_path, access)
    assert row["user_id"] == uid
    assert row["resource"] == "https://colibre.fr/_mcp"


def test_wrong_verifier_rejected(flow_app, monkeypatch):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    app, _ = flow_app
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    uid = auth_db.create_user("sub2@ex.fr", "h")
    _, sub_id = sub_db.create_pending(uid, "colibre-1", "simple")
    sub_db.set_status(sub_id, "active")
    client = app.test_client()
    client.get(f"/_test_login/{uid}")
    cid = _register(client)
    _, challenge = _pkce()
    qs = {
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        "scope": "mcp",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    resp = client.post("/oauth/authorize", query_string=qs, data={"confirm": "yes"})
    code = re.search(r"code=([^&]+)", resp.headers["Location"]).group(1)
    tok = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": cid,
            "code_verifier": "wrong" * 13,
        },
    )
    assert tok.status_code == 400
    assert tok.get_json()["error"] == "invalid_grant"


def _obtain_tokens(client, cid, monkeypatch):
    verifier, challenge = _pkce()
    qs = {
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        "scope": "mcp offline_access",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    resp = client.post("/oauth/authorize", query_string=qs, data={"confirm": "yes"})
    code = re.search(r"code=([^&]+)", resp.headers["Location"]).group(1)
    tok = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": cid,
            "code_verifier": verifier,
        },
    )
    return tok.get_json()


def test_refresh_rotates_and_requires_subscription(flow_app, monkeypatch):
    from src.auth import db as auth_db
    from src.mcp.oauth import store
    from src.subscriptions import db as sub_db

    app, db_path = flow_app
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    uid = auth_db.create_user("ref@ex.fr", "h")
    _, sub_id = sub_db.create_pending(uid, "colibre-1", "simple")
    sub_db.set_status(sub_id, "active")
    client = app.test_client()
    client.get(f"/_test_login/{uid}")
    cid = _register(client)
    first = _obtain_tokens(client, cid, monkeypatch)
    assert "refresh_token" in first

    # Refresh réussi → nouveau refresh (rotation), ancien révoqué.
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": first["refresh_token"],
            "client_id": cid,
        },
    )
    assert r.status_code == 200
    assert r.get_json()["refresh_token"] != first["refresh_token"]
    assert store.get_token_by_refresh(db_path, first["refresh_token"])["revoked_at"]

    # Abonnement perdu → refresh refusé (invalid_grant).
    new_refresh = r.get_json()["refresh_token"]
    monkeypatch.setattr(
        "src.mcp.oauth.consent.has_active_subscription", lambda u: False
    )
    r2 = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": new_refresh,
            "client_id": cid,
        },
    )
    assert r2.status_code == 400
    assert r2.get_json()["error"] == "invalid_grant"
