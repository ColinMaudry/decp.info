import pytest

from src.auth import db
from src.auth import oauth as oauth_module


@pytest.fixture
def fake_userinfo(monkeypatch):
    """Patche authorize_access_token pour éviter tout appel réseau."""

    state = {"userinfo": None, "raise": False}

    def _authorize_access_token():
        if state["raise"]:
            raise RuntimeError("token exchange failed")
        return {"userinfo": state["userinfo"]}

    monkeypatch.setattr(
        oauth_module.oauth.linkedin,
        "authorize_access_token",
        _authorize_access_token,
        raising=False,
    )
    return state


def test_login_route_redirects_to_linkedin(client, monkeypatch):
    from flask import redirect

    monkeypatch.setattr(
        oauth_module.oauth.linkedin,
        "authorize_redirect",
        lambda redirect_uri, **kw: redirect("https://www.linkedin.com/oauth/authorize"),
        raising=False,
    )
    resp = client.get("/auth/linkedin")
    assert resp.status_code == 302
    assert "linkedin.com" in resp.headers["Location"]


def test_callback_creates_user_and_logs_in(client, fake_userinfo, users_db_path):
    db.init_schema()
    fake_userinfo["userinfo"] = {
        "sub": "sub-xyz",
        "email": "newbie@example.com",
        "email_verified": True,
    }
    resp = client.get("/auth/linkedin/callback")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/compte/admin")
    assert db.get_user_by_email("newbie@example.com") is not None


def test_callback_without_email_fails(client, fake_userinfo, users_db_path):
    db.init_schema()
    fake_userinfo["userinfo"] = {"sub": "sub-noemail", "email_verified": True}
    resp = client.get("/auth/linkedin/callback")
    assert resp.status_code == 302
    assert "error=oauth_failed" in resp.headers["Location"]


def test_callback_token_error_redirects(client, fake_userinfo, users_db_path):
    db.init_schema()
    fake_userinfo["raise"] = True
    resp = client.get("/auth/linkedin/callback")
    assert resp.status_code == 302
    assert "error=oauth_failed" in resp.headers["Location"]


def test_callback_user_cancelled_redirects(client, users_db_path):
    db.init_schema()
    resp = client.get("/auth/linkedin/callback?error=user_cancelled_login")
    assert resp.status_code == 302
    assert "error=oauth_cancelled" in resp.headers["Location"]
