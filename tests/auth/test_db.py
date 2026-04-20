import pytest

from src.auth.db import (
    create_user,
    get_conn,
    get_user_by_email,
    get_user_by_id,
    init_schema,
    set_email_verified,
    update_password_hash,
)


def test_init_schema_creates_tables(users_db_path):
    init_schema()
    conn = get_conn()
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"users", "email_verification_tokens", "password_reset_tokens"} <= tables


def test_init_schema_is_idempotent(users_db_path):
    init_schema()
    init_schema()
    conn = get_conn()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = [r[0] for r in tables]
    assert names.count("users") == 1


def test_pragmas_active(users_db_path):
    init_schema()
    conn = get_conn()
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_create_user_and_get_by_email(users_db_path):
    init_schema()
    user_id = create_user("alice@example.com", "hash-bidon")
    assert user_id > 0
    row = get_user_by_email("alice@example.com")
    assert row is not None
    assert row["email"] == "alice@example.com"
    assert row["email_verified"] == 0


def test_email_is_lowercased(users_db_path):
    init_schema()
    create_user("Alice@Example.COM", "hash")
    row = get_user_by_email("alice@example.com")
    assert row is not None
    row_upper = get_user_by_email("ALICE@example.com")
    assert row_upper is not None
    assert row["id"] == row_upper["id"]


def test_duplicate_email_raises(users_db_path):
    init_schema()
    create_user("alice@example.com", "hash")
    with pytest.raises(Exception):
        create_user("alice@example.com", "autre")


def test_get_user_by_id(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    row = get_user_by_id(uid)
    assert row["email"] == "a@b.c"
    assert get_user_by_id(999999) is None


def test_set_email_verified(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    assert get_user_by_id(uid)["email_verified"] == 0
    set_email_verified(uid)
    assert get_user_by_id(uid)["email_verified"] == 1


def test_update_password_hash(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "old")
    update_password_hash(uid, "new")
    assert get_user_by_id(uid)["password_hash"] == "new"
