from werkzeug.security import check_password_hash, generate_password_hash

from src.auth import db


def _login(client, email="a@b.c", password="old-password12"):
    db.init_schema()
    uid = db.create_user(email, generate_password_hash(password))
    db.set_email_verified(uid)
    client.post("/auth/login", data={"email": email, "password": password})
    return uid


def test_change_password_requires_login(client, users_db_path):
    resp = client.post(
        "/auth/change-password",
        data={
            "current_password": "whatever",
            "password": "new-password12",
            "password_confirm": "new-password12",
        },
    )
    assert resp.status_code in (302, 401)


def test_change_password_success(client, users_db_path):
    uid = _login(client)
    resp = client.post(
        "/auth/change-password",
        data={
            "current_password": "old-password12",
            "password": "new-password12",
            "password_confirm": "new-password12",
        },
    )
    assert resp.status_code == 302
    assert "password_changed=1" in resp.headers["Location"]
    row = db.get_user_by_id(uid)
    assert check_password_hash(row["password_hash"], "new-password12")


def test_change_password_wrong_current(client, users_db_path):
    uid = _login(client)
    resp = client.post(
        "/auth/change-password",
        data={
            "current_password": "wrong",
            "password": "new-password12",
            "password_confirm": "new-password12",
        },
    )
    assert "error=invalid_current_password" in resp.headers["Location"]
    row = db.get_user_by_id(uid)
    assert check_password_hash(row["password_hash"], "old-password12")


def test_change_password_short(client, users_db_path):
    _login(client)
    resp = client.post(
        "/auth/change-password",
        data={
            "current_password": "old-password12",
            "password": "short",
            "password_confirm": "short",
        },
    )
    assert "error=password_too_short" in resp.headers["Location"]


def test_change_password_mismatch(client, users_db_path):
    _login(client)
    resp = client.post(
        "/auth/change-password",
        data={
            "current_password": "old-password12",
            "password": "new-password12",
            "password_confirm": "autre-password12",
        },
    )
    assert "error=password_mismatch" in resp.headers["Location"]
