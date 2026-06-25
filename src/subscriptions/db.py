import sqlite3
from datetime import datetime, timezone

from src.auth.db import get_conn

SUBSCRIPTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id                     INTEGER PRIMARY KEY,
    frisbii_customer_handle     TEXT,
    frisbii_subscription_handle TEXT,
    plan                        TEXT,
    status                      TEXT,
    current_period_end          TEXT,
    trial_used                  INTEGER NOT NULL DEFAULT 0,
    created_at                  TEXT NOT NULL,
    updated_at                  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_customer
    ON subscriptions(frisbii_customer_handle);
"""

_ACCESS_STATUSES = ("trial", "active")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema() -> None:
    get_conn().executescript(SUBSCRIPTIONS_SCHEMA)


def create_pending(user_id: int, customer_handle: str, plan: str) -> None:
    now = _now()
    get_conn().execute(
        "INSERT INTO subscriptions "
        "(user_id, frisbii_customer_handle, plan, status, created_at, updated_at) "
        "VALUES (?, ?, ?, 'pending', ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "frisbii_customer_handle=excluded.frisbii_customer_handle, "
        "plan=excluded.plan, status='pending', updated_at=excluded.updated_at",
        (user_id, customer_handle, plan, now, now),
    )


def get_by_user(user_id: int) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute("SELECT * FROM subscriptions WHERE user_id = ?", (user_id,))
        .fetchone()
    )


def get_by_customer(customer_handle: str) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute(
            "SELECT * FROM subscriptions WHERE frisbii_customer_handle = ?",
            (customer_handle,),
        )
        .fetchone()
    )


def update_from_webhook(
    customer_handle: str,
    subscription_handle: str | None,
    status: str,
    current_period_end: str | None,
) -> None:
    trial_flag = 1 if status in _ACCESS_STATUSES else 0
    get_conn().execute(
        "UPDATE subscriptions SET "
        "frisbii_subscription_handle = COALESCE(?, frisbii_subscription_handle), "
        "status = ?, current_period_end = ?, "
        "trial_used = max(trial_used, ?), updated_at = ? "
        "WHERE frisbii_customer_handle = ?",
        (
            subscription_handle,
            status,
            current_period_end,
            trial_flag,
            _now(),
            customer_handle,
        ),
    )


def set_cancelled(user_id: int, current_period_end: str | None) -> None:
    get_conn().execute(
        "UPDATE subscriptions SET status = 'cancelled', current_period_end = ?, "
        "updated_at = ? WHERE user_id = ?",
        (current_period_end, _now(), user_id),
    )


def has_active_subscription(user_id: int) -> bool:
    row = get_by_user(user_id)
    if row is None:
        return False
    if row["status"] in _ACCESS_STATUSES:
        return True
    if row["status"] == "cancelled" and row["current_period_end"]:
        try:
            end = datetime.fromisoformat(
                row["current_period_end"].replace("Z", "+00:00")
            )
            return end > datetime.now(timezone.utc)
        except ValueError:
            return False
    return False


def has_used_trial(user_id: int) -> bool:
    row = get_by_user(user_id)
    return bool(row and row["trial_used"])
