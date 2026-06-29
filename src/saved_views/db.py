import sqlite3
from datetime import datetime, timezone

from src.auth.db import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_views (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    table_name  TEXT NOT NULL DEFAULT 'tableau',
    name        TEXT NOT NULL,
    query       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (user_id, table_name, name)
);
CREATE INDEX IF NOT EXISTS idx_saved_views_user
    ON saved_views(user_id, table_name);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema() -> None:
    get_conn().executescript(SCHEMA)


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


def upsert(user_id: int, table_name: str, name: str, query: str) -> None:
    now = _now()
    get_conn().execute(
        "INSERT INTO saved_views "
        "(user_id, table_name, name, query, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, table_name, name) DO UPDATE SET "
        "query = excluded.query, updated_at = excluded.updated_at",
        (user_id, table_name, name, query, now, now),
    )


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
