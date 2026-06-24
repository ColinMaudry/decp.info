from werkzeug.security import generate_password_hash

from src.auth import db
from src.auth.models import User
from src.auth.routes import resolve_oauth_user


def test_creates_new_user_when_unknown(users_db_path):
    db.init_schema()
    user = resolve_oauth_user("linkedin", "sub-1", "new@example.com", True)
    assert isinstance(user, User)
    row = db.get_user_by_id(int(user.get_id()))
    assert row["email"] == "new@example.com"
    assert row["password_hash"] is None
    assert row["email_verified"] == 1
    assert db.get_oauth_identity("linkedin", "sub-1")["user_id"] == row["id"]


def test_links_to_existing_email_account(users_db_path):
    db.init_schema()
    uid = db.create_user("alice@example.com", generate_password_hash("password12"))
    db.set_email_verified(uid)

    user = resolve_oauth_user("linkedin", "sub-2", "alice@example.com", True)
    assert int(user.get_id()) == uid
    assert db.get_oauth_identity("linkedin", "sub-2")["user_id"] == uid
    # Le compte garde son mot de passe.
    assert db.get_user_by_id(uid)["password_hash"] is not None


def test_links_and_verifies_unverified_existing_account(users_db_path):
    db.init_schema()
    uid = db.create_user("bob@example.com", generate_password_hash("password12"))
    assert db.get_user_by_id(uid)["email_verified"] == 0

    resolve_oauth_user("linkedin", "sub-3", "bob@example.com", True)
    assert db.get_user_by_id(uid)["email_verified"] == 1


def test_returns_same_user_for_known_identity(users_db_path):
    db.init_schema()
    first = resolve_oauth_user("linkedin", "sub-4", "carol@example.com", True)
    second = resolve_oauth_user("linkedin", "sub-4", "carol@example.com", True)
    assert first.get_id() == second.get_id()
    # Pas de doublon d'identité.
    count = (
        db.get_conn()
        .execute(
            "SELECT COUNT(*) FROM oauth_identities WHERE provider='linkedin' AND subject='sub-4'"
        )
        .fetchone()[0]
    )
    assert count == 1
