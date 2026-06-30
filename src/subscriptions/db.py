import sqlite3
from datetime import datetime, timedelta, timezone

from src.auth.db import get_conn

SUBSCRIPTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id                     INTEGER PRIMARY KEY,
    frisbii_customer_handle     TEXT,
    frisbii_subscription_handle TEXT,
    plan                        TEXT,
    prix_ht                     REAL,
    status                      TEXT,
    current_period_end          TEXT,
    trial_used                  INTEGER NOT NULL DEFAULT 0,
    votes_balance               INTEGER NOT NULL DEFAULT 0,
    votes_last_credited_at        TEXT,
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


INITIAL_VOTES = 3
VOTES_PER_WEEK = 3
WEEK_SECONDS = 7 * 24 * 3600


def init_schema() -> None:
    get_conn().executescript(SUBSCRIPTIONS_SCHEMA)


def create_pending(
    user_id: int, customer_handle: str, plan: str, prix_ht: float | None = None
) -> None:
    now = _now()
    get_conn().execute(
        "INSERT INTO subscriptions "
        "(user_id, frisbii_customer_handle, plan, prix_ht, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'pending', ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "frisbii_customer_handle=excluded.frisbii_customer_handle, "
        "plan=excluded.plan, prix_ht=excluded.prix_ht, "
        "status='pending', updated_at=excluded.updated_at",
        (user_id, customer_handle, plan, prix_ht, now, now),
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


def freeze_votes_cursor(user_id: int) -> None:
    """Réactivation après une période sans abonnement : repart de maintenant.

    Ne fait rien si le curseur est NULL (première activation jamais atteinte) :
    les +2 initiaux restent gérés par credit_pending. Ne re-crédite jamais.
    """
    row = get_by_user(user_id)
    if row is None or row["votes_last_credited_at"] is None:
        return
    now = _now()
    get_conn().execute(
        "UPDATE subscriptions SET votes_last_credited_at = ?, updated_at = ? "
        "WHERE user_id = ?",
        (now, now, user_id),
    )


def update_from_webhook(
    customer_handle: str,
    subscription_handle: str | None,
    status: str,
    current_period_end: str | None,
) -> None:
    prev = get_by_customer(customer_handle)
    if prev is not None and prev["status"] == "active" and status != "active":
        credit_pending(prev["user_id"])  # banque les semaines acquises avant gel
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
    if prev is not None and prev["status"] != "active" and status == "active":
        freeze_votes_cursor(prev["user_id"])


def set_cancelled(user_id: int, current_period_end: str | None) -> None:
    credit_pending(
        user_id
    )  # banque les semaines pleines acquises (statut encore actif)
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


def _set_votes(user_id: int, balance: int, cursor_iso: str) -> None:
    get_conn().execute(
        "UPDATE subscriptions SET votes_balance = ?, votes_last_credited_at = ?, "
        "updated_at = ? WHERE user_id = ?",
        (balance, cursor_iso, _now(), user_id),
    )


def credit_pending(user_id: int) -> int:
    """Crédite paresseusement les votes acquis et renvoie le solde courant.

    +VOTES_PER_WEEK à la première activation, puis +VOTES_PER_WEEK par semaine
    pleine. Le solde est cappé à VOTES_PER_WEEK (pas d'accumulation).
    Idempotent : ne crédite que des semaines pleines.
    """
    row = get_by_user(user_id)
    if row is None:
        return 0
    balance = row["votes_balance"] or 0
    if row["status"] != "active":
        return balance
    now = datetime.now(timezone.utc)
    cursor = row["votes_last_credited_at"]
    if cursor is None:
        balance = min(balance + INITIAL_VOTES, VOTES_PER_WEEK)
        _set_votes(user_id, balance, now.isoformat())
        return balance
    cur = datetime.fromisoformat(cursor)
    weeks = int((now - cur).total_seconds() // WEEK_SECONDS)
    if weeks > 0:
        balance = min(balance + weeks * VOTES_PER_WEEK, VOTES_PER_WEEK)
        new_cursor = cur + timedelta(seconds=weeks * WEEK_SECONDS)
        _set_votes(user_id, balance, new_cursor.isoformat())
    return balance


def spend_vote(user_id: int) -> bool:
    """Débite 1 vote si le solde le permet. Renvoie True si un vote a été débité."""
    cur = get_conn().execute(
        "UPDATE subscriptions SET votes_balance = votes_balance - 1, updated_at = ? "
        "WHERE user_id = ? AND votes_balance > 0",
        (_now(), user_id),
    )
    return cur.rowcount > 0


def next_recharge_at(user_id: int) -> datetime | None:
    """Retourne la date du prochain rechargement de votes, ou None si non applicable."""
    row = get_by_user(user_id)
    if not row or not row["votes_last_credited_at"]:
        return None
    cursor = datetime.fromisoformat(row["votes_last_credited_at"])
    return cursor + timedelta(seconds=WEEK_SECONDS)
