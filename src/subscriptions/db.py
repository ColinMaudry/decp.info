import os
import sqlite3
from datetime import datetime, timedelta, timezone

from src.auth.db import get_conn

SUBSCRIPTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id                           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                      INTEGER NOT NULL,
    frisbii_customer_handle      TEXT,
    frisbii_subscription_handle  TEXT,
    plan                         TEXT,
    prix_ht                      REAL,
    status                       TEXT,
    current_period_end           TEXT,
    created_at                   TEXT NOT NULL,
    updated_at                   TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_handle
    ON subscriptions(frisbii_subscription_handle);

CREATE TABLE IF NOT EXISTS subscriber_state (
    user_id                 INTEGER PRIMARY KEY,
    trial_used              INTEGER NOT NULL DEFAULT 0,
    votes_balance           INTEGER NOT NULL DEFAULT 0,
    votes_last_credited_at  TEXT,
    updated_at              TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

_ACCESS_STATUSES = ("trial", "active")

INITIAL_VOTES = 3
VOTES_PER_WEEK = os.getenv("VOTES_PER_WEEK", 5)
WEEK_SECONDS = 7 * 24 * 3600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema() -> None:
    conn = get_conn()
    conn.executescript(SUBSCRIPTIONS_SCHEMA)
    _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(subscriptions)")}
    if "id" not in cols:
        _rebuild_subscriptions_history(conn)


def _rebuild_subscriptions_history(conn: sqlite3.Connection) -> None:
    # L'ancien schéma avait user_id en PRIMARY KEY (1 ligne par utilisateur) et
    # portait aussi l'état cumulatif (votes, essai). SQLite ne peut ni retirer
    # une PRIMARY KEY ni répartir des colonnes vers une autre table via ALTER :
    # on reconstruit la table. foreign_keys OFF pour éviter le cascade-delete
    # pendant le DROP.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            CREATE TABLE subscriptions_new (
                id                           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id                      INTEGER NOT NULL,
                frisbii_customer_handle      TEXT,
                frisbii_subscription_handle  TEXT,
                plan                         TEXT,
                prix_ht                      REAL,
                status                       TEXT,
                current_period_end           TEXT,
                created_at                   TEXT NOT NULL,
                updated_at                   TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "INSERT INTO subscriptions_new (user_id, frisbii_customer_handle, "
            "frisbii_subscription_handle, plan, prix_ht, status, "
            "current_period_end, created_at, updated_at) "
            "SELECT user_id, frisbii_customer_handle, frisbii_subscription_handle, "
            "plan, prix_ht, status, current_period_end, created_at, updated_at "
            "FROM subscriptions"
        )
        conn.execute(
            "INSERT INTO subscriber_state (user_id, trial_used, votes_balance, "
            "votes_last_credited_at, updated_at) "
            "SELECT user_id, trial_used, votes_balance, votes_last_credited_at, "
            "updated_at FROM subscriptions"
        )
        conn.execute("DROP TABLE subscriptions")
        conn.execute("ALTER TABLE subscriptions_new RENAME TO subscriptions")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subscriptions_user "
            "ON subscriptions(user_id)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_handle "
            "ON subscriptions(frisbii_subscription_handle)"
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def get_current(user_id: int) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute(
            "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        .fetchone()
    )


SUBSCRIPTION_STATUSES = ("active", "trial", "cancelled", "expired", "pending")


def list_by_user(user_id: int) -> list[sqlite3.Row]:
    return (
        get_conn()
        .execute(
            "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        )
        .fetchall()
    )


def set_status(subscription_id: int, status: str) -> None:
    get_conn().execute(
        "UPDATE subscriptions SET status = ?, updated_at = ? WHERE id = ?",
        (status, _now(), subscription_id),
    )


def get_by_handle(subscription_handle: str) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute(
            "SELECT * FROM subscriptions WHERE frisbii_subscription_handle = ?",
            (subscription_handle,),
        )
        .fetchone()
    )


def customer_known(customer_handle: str) -> bool:
    row = (
        get_conn()
        .execute(
            "SELECT 1 FROM subscriptions WHERE frisbii_customer_handle = ? LIMIT 1",
            (customer_handle,),
        )
        .fetchone()
    )
    return row is not None


def _next_handle(user_id: int, customer_handle: str) -> str:
    """Prochain handle d'abonnement libre pour cet utilisateur.

    Dérivé du handle customer, donc préfixé par l'environnement (#126) : un
    `colibre-4-1` de production ne peut plus entrer en collision avec le
    `colibre_test-4-1` de test.colibre.fr dans le compte Frisbii partagé.
    """
    prefix = f"{customer_handle}-"
    rows = (
        get_conn()
        .execute(
            "SELECT frisbii_subscription_handle FROM subscriptions WHERE user_id = ?",
            (user_id,),
        )
        .fetchall()
    )
    # Filtrage en Python plutôt qu'en SQL : le préfixe contient un `_`, qui est
    # un joker LIKE en SQLite.
    n = 0
    for row in rows:
        handle = row["frisbii_subscription_handle"] or ""
        if not handle.startswith(prefix):
            continue
        suffix = handle[len(prefix) :]
        if suffix.isdigit():
            n = max(n, int(suffix))
    return f"{prefix}{n + 1}"


def create_pending(
    user_id: int, customer_handle: str, plan: str, prix_ht: float | None = None
) -> tuple[str, int]:
    """Crée une nouvelle ligne d'historique en statut 'pending'.

    Renvoie (handle, subscription_id). Le handle est choisi et enregistré ici,
    avant tout appel à l'API Frisbii.
    """
    now = _now()
    handle = _next_handle(user_id, customer_handle)
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO subscriber_state (user_id, updated_at) VALUES (?, ?)",
        (user_id, now),
    )
    cur = conn.execute(
        "INSERT INTO subscriptions "
        "(user_id, frisbii_customer_handle, frisbii_subscription_handle, plan, "
        "prix_ht, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
        (user_id, customer_handle, handle, plan, prix_ht, now, now),
    )
    return handle, cur.lastrowid


def mark_failed(subscription_id: int) -> None:
    """Marque une ligne comme échouée (échec de l'appel Frisbii après create_pending).

    Le handle reste enregistré (pas de suppression de la ligne) pour ne
    jamais être réutilisé par _next_handle.
    """
    get_conn().execute(
        "UPDATE subscriptions SET status = 'failed', updated_at = ? WHERE id = ?",
        (_now(), subscription_id),
    )


def _get_state(user_id: int) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute("SELECT * FROM subscriber_state WHERE user_id = ?", (user_id,))
        .fetchone()
    )


def get_subscriber_state(user_id: int) -> sqlite3.Row | None:
    return _get_state(user_id)


def freeze_votes_cursor(user_id: int) -> None:
    """Réactivation après une période sans abonnement : repart de maintenant.

    Ne fait rien si le curseur est NULL (première activation jamais atteinte) :
    les +2 initiaux restent gérés par credit_pending. Ne re-crédite jamais.
    """
    row = _get_state(user_id)
    if row is None or row["votes_last_credited_at"] is None:
        return
    now = _now()
    get_conn().execute(
        "UPDATE subscriber_state SET votes_last_credited_at = ?, updated_at = ? "
        "WHERE user_id = ?",
        (now, now, user_id),
    )


def update_from_webhook(
    subscription_handle: str,
    status: str,
    current_period_end: str | None,
) -> None:
    prev = get_by_handle(subscription_handle)
    if prev is None:
        return
    if prev["status"] == "active" and status != "active":
        credit_pending(prev["user_id"])  # banque les semaines acquises avant gel
    get_conn().execute(
        "UPDATE subscriptions SET status = ?, current_period_end = ?, "
        "updated_at = ? WHERE id = ?",
        (status, current_period_end, _now(), prev["id"]),
    )
    if status in _ACCESS_STATUSES:
        get_conn().execute(
            "UPDATE subscriber_state SET trial_used = 1, updated_at = ? "
            "WHERE user_id = ?",
            (_now(), prev["user_id"]),
        )
    if prev["status"] != "active" and status == "active":
        freeze_votes_cursor(prev["user_id"])


def set_cancelled(subscription_id: int, current_period_end: str | None) -> None:
    row = (
        get_conn()
        .execute("SELECT user_id FROM subscriptions WHERE id = ?", (subscription_id,))
        .fetchone()
    )
    if row is None:
        return
    credit_pending(row["user_id"])  # banque les semaines pleines acquises
    get_conn().execute(
        "UPDATE subscriptions SET status = 'cancelled', current_period_end = ?, "
        "updated_at = ? WHERE id = ?",
        (current_period_end, _now(), subscription_id),
    )


def has_active_subscription(user_id: int) -> bool:
    row = get_current(user_id)
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
    row = _get_state(user_id)
    return bool(row and row["trial_used"])


def _set_votes(user_id: int, balance: int, cursor_iso: str) -> None:
    get_conn().execute(
        "UPDATE subscriber_state SET votes_balance = ?, votes_last_credited_at = ?, "
        "updated_at = ? WHERE user_id = ?",
        (balance, cursor_iso, _now(), user_id),
    )


def credit_pending(user_id: int) -> int:
    """Crédite paresseusement les votes acquis et renvoie le solde courant.

    +VOTES_PER_WEEK à la première activation, puis +VOTES_PER_WEEK par semaine
    pleine. Le solde est cappé à VOTES_PER_WEEK (pas d'accumulation).
    Idempotent : ne crédite que des semaines pleines.

    Sous TOUS_ABONNES, les accès gratuits n'ont pas de ligne `subscriptions` :
    on crée `subscriber_state` à la volée et on lève le garde-fou sur le statut,
    pour que solde et recharge hebdomadaire fonctionnent comme pour un abonné.
    """
    from src.utils import TOUS_ABONNES

    if TOUS_ABONNES:
        # Le SELECT ... FROM users garantit qu'aucune ligne n'est insérée pour un
        # user_id inconnu : OR IGNORE n'avale PAS les violations de clé étrangère
        # (seulement UNIQUE/NOT NULL/CHECK), on aurait donc une IntegrityError.
        get_conn().execute(
            "INSERT OR IGNORE INTO subscriber_state (user_id, updated_at) "
            "SELECT id, ? FROM users WHERE id = ?",
            (_now(), user_id),
        )
    state = _get_state(user_id)
    if state is None:
        return 0
    balance = state["votes_balance"] or 0
    current = get_current(user_id)
    if not TOUS_ABONNES and (current is None or current["status"] != "active"):
        return balance
    now = datetime.now(timezone.utc)
    cursor = state["votes_last_credited_at"]
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
        "UPDATE subscriber_state SET votes_balance = votes_balance - 1, "
        "updated_at = ? WHERE user_id = ? AND votes_balance > 0",
        (_now(), user_id),
    )
    return cur.rowcount > 0


def next_recharge_at(user_id: int) -> datetime | None:
    """Retourne la date du prochain rechargement de votes, ou None si non applicable."""
    row = _get_state(user_id)
    if not row or not row["votes_last_credited_at"]:
        return None
    cursor = datetime.fromisoformat(row["votes_last_credited_at"])
    return cursor + timedelta(seconds=WEEK_SECONDS)
