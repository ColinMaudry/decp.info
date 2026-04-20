from src.auth import db
from src.auth.tokens import (
    consume_password_reset_token,
    consume_verification_token,
    create_password_reset_token,
    create_verification_token,
    hash_token,
)


def test_hash_token_is_stable():
    t = "abc123"
    assert hash_token(t) == hash_token(t)
    assert hash_token(t) != hash_token("abc124")
    assert len(hash_token(t)) == 64  # sha256 hex


def test_create_verification_token_returns_plain_token(users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    plain = create_verification_token(uid)
    assert isinstance(plain, str)
    assert len(plain) >= 32
    # stocké en DB sous forme hashée
    row = db.find_email_verification_token(hash_token(plain))
    assert row is not None
    assert row["user_id"] == uid


def test_consume_verification_token_succeeds_once(users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    plain = create_verification_token(uid)
    user_id = consume_verification_token(plain)
    assert user_id == uid
    # usage unique : les tokens de cet user sont supprimés
    assert consume_verification_token(plain) is None


def test_consume_invalid_verification_token(users_db_path):
    db.init_schema()
    assert consume_verification_token("n-existe-pas") is None


def test_verification_token_expires(users_db_path, monkeypatch):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    plain = create_verification_token(uid, expires_in_hours=-1)
    assert consume_verification_token(plain) is None


def test_create_password_reset_token_deletes_previous(users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    old = create_password_reset_token(uid)
    new = create_password_reset_token(uid)
    # l'ancien a été supprimé
    assert consume_password_reset_token(old) is None
    # le nouveau fonctionne
    assert consume_password_reset_token(new) == uid


def test_consume_password_reset_token_is_single_use(users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    plain = create_password_reset_token(uid)
    assert consume_password_reset_token(plain) == uid
    assert consume_password_reset_token(plain) is None
