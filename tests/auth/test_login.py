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
    assert resp.headers["Location"].endswith("/compte")


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
    assert resp.headers["Location"].endswith("/compte")


def test_logout_clears_session(client, users_db_path):
    _make_verified_user()
    client.post("/auth/login", data={"email": "a@b.c", "password": "password12"})
    resp = client.post("/auth/logout")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
