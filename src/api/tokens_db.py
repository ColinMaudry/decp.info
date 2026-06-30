import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

TOKEN_PREFIX = "colibre_"

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_tokens (
    id           INTEGER PRIMARY KEY,
    token_hash   TEXT NOT NULL UNIQUE,
    label        TEXT NOT NULL,
    user_id      INTEGER,
    created_at   TEXT NOT NULL,
    last_used_at TEXT,
    count_total  INTEGER NOT NULL DEFAULT 0,
    revoked_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens(token_hash);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@contextmanager
def _connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_schema(db_path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def create_token(db_path, label: str, user_id: int | None = None) -> tuple[str, int]:
    token = TOKEN_PREFIX + secrets.token_hex(32)
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO api_tokens (token_hash, label, user_id, created_at) "
            "VALUES (?, ?, ?, ?)",
            (_hash(token), label, user_id, _utcnow_iso()),
        )
        conn.commit()
        return token, cur.lastrowid


def get_token_by_plaintext(db_path, token: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM api_tokens WHERE token_hash = ?",
            (_hash(token),),
        ).fetchone()
    return dict(row) if row else None


def revoke_token(db_path, token_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE api_tokens SET revoked_at = ? WHERE id = ?",
            (_utcnow_iso(), token_id),
        )
        conn.commit()


def increment_usage(db_path, token_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE api_tokens "
            "SET count_total = count_total + 1, last_used_at = ? "
            "WHERE id = ?",
            (_utcnow_iso(), token_id),
        )
        conn.commit()


def list_tokens(db_path) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM api_tokens ORDER BY id").fetchall()
    return [dict(r) for r in rows]
