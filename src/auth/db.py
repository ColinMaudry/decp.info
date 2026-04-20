import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

_conn: sqlite3.Connection | None = None
_conn_lock = Lock()

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


def _db_path() -> Path:
    return Path(os.getenv("USERS_DB_PATH", "users.sqlite"))


def get_conn() -> sqlite3.Connection:
    global _conn
    with _conn_lock:
        if _conn is None:
            _conn = sqlite3.connect(
                str(_db_path()), check_same_thread=False, isolation_level=None
            )
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA foreign_keys = ON")
            _conn.execute("PRAGMA journal_mode = WAL")
        return _conn


def reset_conn_for_tests() -> None:
    global _conn
    with _conn_lock:
        if _conn is not None:
            _conn.close()
        _conn = None


def init_schema() -> None:
    conn = get_conn()
    conn.executescript(USERS_SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_user(email: str, password_hash: str) -> int:
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, email_verified, created_at, updated_at) "
        "VALUES (?, ?, 0, ?, ?)",
        (email.lower(), password_hash, now, now),
    )
    return cur.lastrowid


def get_user_by_email(email: str) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
        .fetchone()
    )


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    return get_conn().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def set_email_verified(user_id: int) -> None:
    get_conn().execute(
        "UPDATE users SET email_verified = 1, updated_at = ? WHERE id = ?",
        (_now(), user_id),
    )


def update_password_hash(user_id: int, password_hash: str) -> None:
    get_conn().execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (password_hash, _now(), user_id),
    )


def delete_user(user_id: int) -> None:
    get_conn().execute("DELETE FROM users WHERE id = ?", (user_id,))
