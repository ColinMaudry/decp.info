import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS mcp_usage (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER,
    token_id   INTEGER,
    kind       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mcp_usage_user ON mcp_usage(user_id, created_at);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def record(db_path, user_id: int, token_id: int, kind: str) -> None:
    """Journalise une requête /_mcp authentifiée. Best-effort : n'échoue jamais."""
    try:
        with _connect(db_path) as conn:
            conn.execute(
                "INSERT INTO mcp_usage (user_id, token_id, kind, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, token_id, kind, _utcnow_iso()),
            )
            conn.commit()
    except sqlite3.Error:
        pass


def count_since(db_path, user_id: int, iso_ts: str) -> int:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM mcp_usage WHERE user_id = ? AND created_at >= ?",
            (user_id, iso_ts),
        ).fetchone()
    return row[0]


def purge_older_than(db_path, days: int = 90) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
        timespec="seconds"
    )
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM mcp_usage WHERE created_at < ?", (cutoff,))
        conn.commit()
