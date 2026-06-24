from werkzeug.security import generate_password_hash

from src.auth import db


def _login(client, email="old@example.fr", password="password12"):
    db.init_schema()
    uid = db.create_user(email, generate_password_hash(password))
    db.set_email_verified(uid)
    client.post("/auth/login", data={"email": email, "password": password})
    return uid


def test_change_email_requires_login(client, users_db_path):
    resp = client.post("/auth/change-email", data={"email": "x@y.z"})
    assert resp.status_code in (302, 401)


def test_change_email_sets_pending_and_sends_mail(client, users_db_path, mail_outbox):
    uid = _login(client)
    resp = client.post("/auth/change-email", data={"email": "new@example.fr"})
    assert resp.status_code == 302
    assert "email_pending=1" in resp.headers["Location"]
    assert db.get_user_by_id(uid)["pending_email"] == "new@example.fr"
    assert db.get_user_by_id(uid)["email"] == "old@example.fr"  # pas encore changé
    assert mail_outbox[0].recipients == ["new@example.fr"]


def test_change_email_invalid(client, users_db_path, mail_outbox):
    _login(client)
    resp = client.post("/auth/change-email", data={"email": "pas-un-email"})
    assert "error=invalid_email" in resp.headers["Location"]
    assert mail_outbox == []


def test_change_email_already_taken(client, users_db_path, mail_outbox):
    _login(client)
    db.create_user("taken@example.fr", generate_password_hash("password12"))
    resp = client.post("/auth/change-email", data={"email": "taken@example.fr"})
    assert "error=email_taken" in resp.headers["Location"]
    assert mail_outbox == []


def test_confirm_email_change_promotes(client, users_db_path, mail_outbox):
    from src.auth import tokens

    uid = _login(client)
    client.post("/auth/change-email", data={"email": "new@example.fr"})
    token = tokens.create_verification_token(uid)
    resp = client.get(f"/auth/confirm-email-change?token={token}")
    assert resp.status_code == 302
    assert "email_changed=1" in resp.headers["Location"]
    assert db.get_user_by_id(uid)["email"] == "new@example.fr"
