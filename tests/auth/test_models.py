from src.auth import db
from src.auth.models import User, load_user


def test_user_from_row(users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "hash")
    db.set_email_verified(uid)
    row = db.get_user_by_id(uid)
    user = User(row)
    assert user.id == uid
    assert user.email == "a@b.c"
    assert user.is_authenticated is True
    assert user.is_active is True
    assert user.is_anonymous is False
    assert user.get_id() == str(uid)


def test_load_user_returns_none_if_missing(users_db_path):
    db.init_schema()
    assert load_user("999999") is None


def test_load_user_returns_user(users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    user = load_user(str(uid))
    assert user is not None
    assert user.id == uid
