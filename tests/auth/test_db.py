from src.auth.db import get_conn, init_schema


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
