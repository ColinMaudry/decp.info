import pytest

from src.auth import db
from src.auth import oauth as oauth_module


@pytest.fixture
def fake_userinfo(monkeypatch):
    """Évite tout appel réseau LinkedIn.

    La route `linkedin_callback` échange d'abord le code via
    `authorize_access_token()` (dont la valeur de retour est ignorée), puis
    récupère le profil par un appel séparé `oauth.linkedin.get(.../userinfo)`.
    On mocke donc les deux : `authorize_access_token` pour réussir/échouer
    l'échange, et `.get()` pour renvoyer le userinfo.
    """

    state = {"userinfo": None, "raise": False}

    def _authorize_access_token():
        if state["raise"]:
            raise RuntimeError("token exchange failed")
        return {"access_token": "fake-token"}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return state["userinfo"]

    def _get(url, *args, **kwargs):
        return _Resp()

    monkeypatch.setattr(
        oauth_module.oauth.linkedin,
        "authorize_access_token",
        _authorize_access_token,
        raising=False,
    )
    monkeypatch.setattr(oauth_module.oauth.linkedin, "get", _get, raising=False)
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
    location = resp.headers["Location"]
    # Nouvel utilisateur sans abonnement → _post_login_url renvoie vers
    # /compte/abonnement (et non /compte/admin, réservé aux abonnés actifs).
    assert location.startswith("/compte/abonnement")
    # Création de compte via LinkedIn : déclenche `account_created` côté
    # navigateur (src/assets/goals.js).
    assert "compte_cree=linkedin" in location
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


def test_connexion_layout_has_linkedin_button():
    import src.app  # noqa: F401 - Initialize Dash app before importing pages
    from src.pages.connexion import layout

    html_str = str(layout())
    assert "Connexion avec LinkedIn" in html_str
    assert "/auth/linkedin" in html_str


def test_connexion_layout_shows_oauth_error():
    import src.app  # noqa: F401 - Initialize Dash app before importing pages
    from src.pages.connexion import layout

    assert "LinkedIn" in str(layout(error="oauth_failed"))


def test_inscription_layout_has_linkedin_button():
    import src.app  # noqa: F401 - Initialize Dash app before importing pages
    from src.pages.inscription import layout

    html_str = str(layout())
    assert "Connexion avec LinkedIn" in html_str
    assert "/auth/linkedin" in html_str
