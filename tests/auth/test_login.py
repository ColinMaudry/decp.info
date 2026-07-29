from werkzeug.security import generate_password_hash

from src.auth import db


def _make_verified_user(email="a@b.c", password="password12"):
    db.init_schema()
    uid = db.create_user(email, generate_password_hash(password))
    db.set_email_verified(uid)
    return uid


def test_login_success(client, users_db_path):
    _make_verified_user()
    resp = client.post(
        "/auth/login",
        data={"email": "a@b.c", "password": "password12"},
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/compte/abonnement")


def test_login_wrong_password(client, users_db_path):
    _make_verified_user()
    resp = client.post(
        "/auth/login", data={"email": "a@b.c", "password": "wrong-password"}
    )
    assert "error=invalid_credentials" in resp.headers["Location"]


def test_login_unknown_email_same_error(client, users_db_path):
    db.init_schema()
    resp = client.post(
        "/auth/login",
        data={"email": "inexistant@example.com", "password": "x" * 12},
    )
    assert "error=invalid_credentials" in resp.headers["Location"]


def test_login_unverified_user(client, users_db_path):
    db.init_schema()
    db.create_user("a@b.c", generate_password_hash("password12"))
    resp = client.post("/auth/login", data={"email": "a@b.c", "password": "password12"})
    assert "error=email_not_verified" in resp.headers["Location"]


def test_login_respects_safe_next(client, users_db_path):
    _make_verified_user()
    resp = client.post(
        "/auth/login",
        data={"email": "a@b.c", "password": "password12", "next": "/tableau"},
    )
    assert resp.headers["Location"].endswith("/tableau")


def test_login_rejects_absolute_next(client, users_db_path):
    _make_verified_user()
    resp = client.post(
        "/auth/login",
        data={
            "email": "a@b.c",
            "password": "password12",
            "next": "https://evil.com",
        },
    )
    assert resp.headers["Location"].endswith("/compte/abonnement")


def test_logout_clears_session(client, users_db_path):
    _make_verified_user()
    client.post("/auth/login", data={"email": "a@b.c", "password": "password12"})
    resp = client.post("/auth/logout")
    assert resp.status_code == 302
    # `?deconnexion=1` déclenche le reset du contact Chatwoot côté client.
    assert resp.headers["Location"] == "/?deconnexion=1"


# --- Tests CSRF (protection active, comme en production) ---


def test_login_rejects_missing_csrf_token(csrf_client):
    """POST /auth/login sans token CSRF → 400.

    Régression : avec prevent_initial_call=True sur _fill_csrf_inputs, le token
    n'était pas injecté dans le formulaire lors du chargement initial de /connexion.
    """
    resp = csrf_client.post(
        "/auth/login",
        data={"email": "a@b.c", "password": "password12"},
    )
    assert resp.status_code == 400


def test_login_accepts_valid_csrf_token(csrf_client, users_db_path):
    """POST /auth/login avec token CSRF valide → 302."""
    _make_verified_user()
    token = csrf_client.get("/_test/csrf").data.decode()
    resp = csrf_client.post(
        "/auth/login",
        data={"email": "a@b.c", "password": "password12", "csrf_token": token},
    )
    assert resp.status_code == 302
