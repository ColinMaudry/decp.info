import sqlite3
from datetime import datetime, timezone

from src.auth.db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_action(
    admin_email: str, action: str, target_user_id: int | None, details: str | None
) -> None:
    get_conn().execute(
        "INSERT INTO admin_actions (admin_email, action, target_user_id, details, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (admin_email, action, target_user_id, details, _now()),
    )


def list_actions(limit: int = 200) -> list[sqlite3.Row]:
    return (
        get_conn()
        .execute("SELECT * FROM admin_actions ORDER BY id DESC LIMIT ?", (limit,))
        .fetchall()
    )
