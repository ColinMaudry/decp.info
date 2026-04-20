from src.auth import db


def _signup(client, email="alice@example.com", password="password12", confirm=None):
    return client.post(
        "/auth/signup",
        data={
            "email": email,
            "password": password,
            "password_confirm": confirm if confirm is not None else password,
        },
    )


def test_signup_creates_unverified_user(client, mail_outbox):
    resp = _signup(client)
    assert resp.status_code == 302
    assert "pending_verification=1" in resp.headers["Location"]
    row = db.get_user_by_email("alice@example.com")
    assert row is not None
    assert row["email_verified"] == 0
    assert len(mail_outbox) == 1
    assert mail_outbox[0].recipients == ["alice@example.com"]


def test_signup_rejects_short_password(client, mail_outbox):
    resp = _signup(client, password="short", confirm="short")
    assert resp.status_code == 302
    assert "error=password_too_short" in resp.headers["Location"]
    assert db.get_user_by_email("alice@example.com") is None
    assert len(mail_outbox) == 0


def test_signup_rejects_mismatched_passwords(client, mail_outbox):
    resp = _signup(client, password="password12", confirm="different12")
    assert "error=password_mismatch" in resp.headers["Location"]
    assert db.get_user_by_email("alice@example.com") is None
    assert len(mail_outbox) == 0


def test_signup_rejects_invalid_email(client, mail_outbox):
    resp = _signup(client, email="pas-un-email")
    assert "error=invalid_email" in resp.headers["Location"]
    assert len(mail_outbox) == 0


def test_signup_rejects_duplicate_email(client, mail_outbox):
    _signup(client)
    resp = _signup(client)
    assert "error=email_taken" in resp.headers["Location"]
    assert len(mail_outbox) == 1  # seul le premier signup a envoyé l'email


def test_signup_email_lowercased(client, mail_outbox):
    _signup(client, email="Alice@Example.COM")
    assert db.get_user_by_email("alice@example.com") is not None
