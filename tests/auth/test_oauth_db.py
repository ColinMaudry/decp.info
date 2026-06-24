import sqlite3

import pytest

from src.auth import db


def test_oauth_identities_table_created(users_db_path):
    db.init_schema()
    tables = {
        r[0]
        for r in db.get_conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "oauth_identities" in tables


def test_password_hash_is_nullable_on_fresh_schema(users_db_path):
    db.init_schema()
    cols = {r["name"]: r for r in db.get_conn().execute("PRAGMA table_info(users)")}
    assert cols["password_hash"]["notnull"] == 0


def test_create_oauth_user(users_db_path):
    db.init_schema()
    uid = db.create_oauth_user("oauth@example.com")
    row = db.get_user_by_id(uid)
    assert row["email"] == "oauth@example.com"
    assert row["password_hash"] is None
    assert row["email_verified"] == 1


def test_link_and_get_oauth_identity(users_db_path):
    db.init_schema()
    uid = db.create_oauth_user("oauth@example.com")
    assert db.get_oauth_identity("linkedin", "sub-123") is None
    db.link_oauth_identity("linkedin", "sub-123", uid)
    row = db.get_oauth_identity("linkedin", "sub-123")
    assert row["user_id"] == uid


def test_oauth_identity_pk_prevents_duplicate(users_db_path):
    db.init_schema()
    uid = db.create_oauth_user("oauth@example.com")
    db.link_oauth_identity("linkedin", "sub-123", uid)
    with pytest.raises(sqlite3.IntegrityError):
        db.link_oauth_identity("linkedin", "sub-123", uid)


def test_migration_makes_legacy_password_hash_nullable(users_db_path):
    # Simule un schéma hérité où password_hash est NOT NULL.
    conn = db.get_conn()
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            email_verified INTEGER NOT NULL DEFAULT 0,
            pending_email TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE email_verification_tokens (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    now = db._now()
    conn.execute(
        "INSERT INTO users (id, email, password_hash, email_verified, created_at, updated_at)"
        " VALUES (1, 'legacy@example.com', 'hash', 1, ?, ?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO email_verification_tokens (token_hash, user_id, expires_at, created_at)"
        " VALUES ('tok', 1, ?, ?)",
        (now, now),
    )

    db.init_schema()  # déclenche _migrate

    cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(users)")}
    assert cols["password_hash"]["notnull"] == 0
    # Données préservées, pas de cascade-delete déclenchée pendant la reconstruction.
    assert db.get_user_by_id(1)["email"] == "legacy@example.com"
    assert (
        conn.execute("SELECT COUNT(*) FROM email_verification_tokens").fetchone()[0]
        == 1
    )
