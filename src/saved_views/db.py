import secrets
import sqlite3
import string
from datetime import datetime, timezone

from src.auth.db import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_views (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    table_name  TEXT NOT NULL DEFAULT 'tableau',
    name        TEXT NOT NULL,
    query       TEXT NOT NULL,
    token       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (user_id, table_name, name)
);
CREATE INDEX IF NOT EXISTS idx_saved_views_user
    ON saved_views(user_id, table_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_saved_views_token
    ON saved_views(token);
"""

_TOKEN_ALPHABET = string.ascii_letters + string.digits  # base62


def generate_token(length: int = 6) -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(length))


def _unique_token(conn) -> str:
    while True:
        token = generate_token()
        exists = conn.execute(
            "SELECT 1 FROM saved_views WHERE token = ?", (token,)
        ).fetchone()
        if exists is None:
            return token


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    # Backfill des lignes pré-migration (token NULL). L'index unique tolère
    # plusieurs NULL transitoires ; on attribue un jeton à chacune. Idempotent :
    # sans effet une fois toutes les lignes pourvues.
    null_rows = conn.execute(
        "SELECT id FROM saved_views WHERE token IS NULL"
    ).fetchall()
    for row in null_rows:
        conn.execute(
            "UPDATE saved_views SET token = ? WHERE id = ?",
            (_unique_token(conn), row["id"]),
        )


def list_views(user_id: int, table_name: str = "tableau") -> list[sqlite3.Row]:
    return (
        get_conn()
        .execute(
            "SELECT * FROM saved_views WHERE user_id = ? AND table_name = ? "
            "ORDER BY name COLLATE NOCASE",
            (user_id, table_name),
        )
        .fetchall()
    )


def get(view_id: int, user_id: int) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute(
            "SELECT * FROM saved_views WHERE id = ? AND user_id = ?",
            (view_id, user_id),
        )
        .fetchone()
    )


def get_by_token(token: str) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute("SELECT * FROM saved_views WHERE token = ?", (token,))
        .fetchone()
    )


def upsert(user_id: int, table_name: str, name: str, query: str) -> str:
    now = _now()
    conn = get_conn()
    # Jeton candidat, utilisé uniquement en cas d'INSERT réel ; à l'écrasement
    # (ON CONFLICT ... DO UPDATE), `token` n'est pas dans le SET → conservé.
    conn.execute(
        "INSERT INTO saved_views "
        "(user_id, table_name, name, query, token, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, table_name, name) DO UPDATE SET "
        "query = excluded.query, updated_at = excluded.updated_at",
        (user_id, table_name, name, query, _unique_token(conn), now, now),
    )
    row = conn.execute(
        "SELECT token FROM saved_views "
        "WHERE user_id = ? AND table_name = ? AND name = ?",
        (user_id, table_name, name),
    ).fetchone()
    return row["token"]


def rename(view_id: int, user_id: int, new_name: str) -> None:
    get_conn().execute(
        "UPDATE saved_views SET name = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (new_name, _now(), view_id, user_id),
    )


def delete(view_id: int, user_id: int) -> None:
    get_conn().execute(
        "DELETE FROM saved_views WHERE id = ? AND user_id = ?",
        (view_id, user_id),
    )
