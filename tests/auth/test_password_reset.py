from werkzeug.security import check_password_hash, generate_password_hash

from src.auth import db, tokens


def _make_user():
    db.init_schema()
    uid = db.create_user("a@b.c", generate_password_hash("old-password12"))
    db.set_email_verified(uid)
    return uid


def test_request_reset_sends_email_for_existing_user(
    client, mail_outbox, users_db_path
):
    _make_user()
    resp = client.post("/auth/request-password-reset", data={"email": "a@b.c"})
    assert resp.status_code == 302
    assert "pending=1" in resp.headers["Location"]
    assert len(mail_outbox) == 1


def test_request_reset_same_response_for_unknown_email(
    client, mail_outbox, users_db_path
):
    db.init_schema()
    resp = client.post("/auth/request-password-reset", data={"email": "absent@b.c"})
    assert "pending=1" in resp.headers["Location"]
    assert len(mail_outbox) == 0


def test_perform_reset_with_valid_token(client, users_db_path):
    uid = _make_user()
    token = tokens.create_password_reset_token(uid)
    resp = client.post(
        "/auth/reset-password",
        data={
            "token": token,
            "password": "new-password12",
            "password_confirm": "new-password12",
        },
    )
    assert resp.status_code == 302
    assert "password_changed=1" in resp.headers["Location"]
    row = db.get_user_by_id(uid)
    assert check_password_hash(row["password_hash"], "new-password12")


def test_perform_reset_rejects_expired_token(client, users_db_path):
    uid = _make_user()
    token = tokens.create_password_reset_token(uid, expires_in_hours=-1)
    resp = client.post(
        "/auth/reset-password",
        data={
            "token": token,
            "password": "new-password12",
            "password_confirm": "new-password12",
        },
    )
    assert "error=invalid_token" in resp.headers["Location"]


def test_perform_reset_rejects_short_password(client, users_db_path):
    uid = _make_user()
    token = tokens.create_password_reset_token(uid)
    resp = client.post(
        "/auth/reset-password",
        data={"token": token, "password": "short", "password_confirm": "short"},
    )
    assert "error=password_too_short" in resp.headers["Location"]


def test_perform_reset_rejects_mismatched(client, users_db_path):
    uid = _make_user()
    token = tokens.create_password_reset_token(uid)
    resp = client.post(
        "/auth/reset-password",
        data={
            "token": token,
            "password": "new-password12",
            "password_confirm": "other-password99",
        },
    )
    assert "error=password_mismatch" in resp.headers["Location"]
