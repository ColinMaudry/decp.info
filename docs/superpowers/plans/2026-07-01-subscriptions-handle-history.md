# Handle d'abonnement personnalisé + historique des abonnements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer `generate_handle: true` par un handle choisi par colibre
(`abo-{user_id}-{N}`, unique), en faisant évoluer `subscriptions` vers un
historique multi-lignes et en introduisant `subscriber_state` pour l'état
cumulatif (votes, essai) de l'utilisateur.

**Architecture:** `subscriptions/db.py` est réécrit intégralement (schéma,
migration par reconstruction de table, toute l'API) car ses fonctions sont
étroitement couplées ; `client.py`, `routes.py` et `compte_abonnement.py`
sont ajustés en tâches séparées une fois la nouvelle API de `db.py`
disponible.

**Tech Stack:** Python, Flask, SQLite (via `src.auth.db.get_conn`), pytest.

## Global Constraints

- Le préfixe du handle est `abo` : format exact `abo-{user_id}-{N}`.
- Le handle est écrit par colibre dans `create_pending`, **avant** l'appel à
  l'API Frisbii — jamais par le webhook.
- Chaque tentative de souscription crée une nouvelle ligne dans
  `subscriptions` (pas de réutilisation d'une ligne `pending` existante).
- Une ligne dont l'appel Frisbii a échoué passe au statut `failed` (jamais
  supprimée), pour ne jamais réutiliser son handle.
- `trial_used`, `votes_balance`, `votes_last_credited_at` vivent dans la
  nouvelle table `subscriber_state` (1 ligne par utilisateur), pas dans
  `subscriptions`.
- Design de référence :
  `docs/superpowers/specs/2026-07-01-subscriptions-handle-history-design.md`.
- Lancer les tests avec `uv run pytest` (l'activation du venv via le Bash
  tool ne met pas PATH à jour de façon fiable dans cet environnement).

---

## Task 1: `subscriptions/db.py` — schéma, migration, API complète

**Files:**

- Modify: `src/subscriptions/db.py` (réécriture complète)
- Modify: `tests/subscriptions/test_db.py` (réécriture complète)

**Interfaces:**

- Produces (utilisées par les tâches suivantes) :

  - `init_schema() -> None`
  - `get_current(user_id: int) -> sqlite3.Row | None`
  - `get_by_handle(subscription_handle: str) -> sqlite3.Row | None`
  - `customer_known(customer_handle: str) -> bool`
  - `create_pending(user_id: int, customer_handle: str, plan: str, prix_ht: float | None = None) -> tuple[str, int]`
    (renvoie `(handle, subscription_id)`)
  - `mark_failed(subscription_id: int) -> None`
  - `update_from_webhook(subscription_handle: str, status: str, current_period_end: str | None) -> None`
  - `set_cancelled(subscription_id: int, current_period_end: str | None) -> None`
  - `has_active_subscription(user_id: int) -> bool`
  - `has_used_trial(user_id: int) -> bool`
  - `credit_pending(user_id: int) -> int`
  - `spend_vote(user_id: int) -> bool`
  - `next_recharge_at(user_id: int) -> datetime | None`
  - `freeze_votes_cursor(user_id: int) -> None`
  - `INITIAL_VOTES`, `VOTES_PER_WEEK` (constantes, inchangées)

- [ ] **Step 1: Écrire le nouveau `src/subscriptions/db.py` (schéma + migration + API)**

Remplacer l'intégralité du fichier `src/subscriptions/db.py` par :

```python
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
VOTES_PER_WEEK = 3
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


def _next_handle(user_id: int) -> str:
    prefix = f"abo-{user_id}-"
    rows = (
        get_conn()
        .execute(
            "SELECT frisbii_subscription_handle FROM subscriptions "
            "WHERE user_id = ? AND frisbii_subscription_handle LIKE ?",
            (user_id, f"{prefix}%"),
        )
        .fetchall()
    )
    n = 0
    for row in rows:
        suffix = row["frisbii_subscription_handle"][len(prefix) :]
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
    handle = _next_handle(user_id)
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
    """
    state = _get_state(user_id)
    if state is None:
        return 0
    balance = state["votes_balance"] or 0
    current = get_current(user_id)
    if current is None or current["status"] != "active":
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
```

- [ ] **Step 2: Écrire le nouveau `tests/subscriptions/test_db.py`**

Remplacer l'intégralité du fichier `tests/subscriptions/test_db.py` par :

```python
from datetime import datetime, timedelta, timezone

from src.auth import db as auth_db
from src.auth.db import get_conn
from src.subscriptions import db


def _future():
    return (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()


def _past():
    return (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def _activate(uid, cursor_iso=None):
    """Met l'abonnement en statut actif avec un curseur d'accumulation donné."""
    row = db.get_current(uid)
    get_conn().execute(
        "UPDATE subscriptions SET status = 'active' WHERE id = ?", (row["id"],)
    )
    get_conn().execute(
        "UPDATE subscriber_state SET votes_last_credited_at = ? WHERE user_id = ?",
        (cursor_iso, uid),
    )


def test_init_schema_creates_tables(users_db_path):
    db.init_schema()
    conn = auth_db.get_conn()
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "subscriptions" in tables
    assert "subscriber_state" in tables


def test_init_schema_migrates_old_single_row_subscriptions(users_db_path):
    auth_db.init_schema()
    uid = auth_db.create_user("legacy@ex.fr", "hash")
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE subscriptions (
            user_id                     INTEGER PRIMARY KEY,
            frisbii_customer_handle     TEXT,
            frisbii_subscription_handle TEXT,
            plan                        TEXT,
            prix_ht                     REAL,
            status                      TEXT,
            current_period_end          TEXT,
            trial_used                  INTEGER NOT NULL DEFAULT 0,
            votes_balance               INTEGER NOT NULL DEFAULT 0,
            votes_last_credited_at      TEXT,
            created_at                  TEXT NOT NULL,
            updated_at                  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "INSERT INTO subscriptions (user_id, frisbii_customer_handle, "
        "frisbii_subscription_handle, plan, status, trial_used, votes_balance, "
        "votes_last_credited_at, created_at, updated_at) "
        "VALUES (?, 'colibre-legacy', 'sub_legacy', 'simple', 'active', 1, 2, "
        "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', "
        "'2026-01-01T00:00:00+00:00')",
        (uid,),
    )

    db.init_schema()

    cols = {row["name"] for row in conn.execute("PRAGMA table_info(subscriptions)")}
    assert "id" in cols

    row = db.get_current(uid)
    assert row["frisbii_subscription_handle"] == "sub_legacy"
    assert row["status"] == "active"

    state = conn.execute(
        "SELECT * FROM subscriber_state WHERE user_id = ?", (uid,)
    ).fetchone()
    assert state["trial_used"] == 1
    assert state["votes_balance"] == 2
    assert state["votes_last_credited_at"] == "2026-01-01T00:00:00+00:00"


def test_create_pending_and_get_current(users_db_path):
    db.init_schema()
    uid = _make_user()
    handle, subscription_id = db.create_pending(uid, "colibre-1", "simple")
    assert handle == f"abo-{uid}-1"
    row = db.get_current(uid)
    assert row["id"] == subscription_id
    assert row["status"] == "pending"
    assert row["plan"] == "simple"
    assert row["frisbii_customer_handle"] == "colibre-1"
    assert row["frisbii_subscription_handle"] == handle


def test_create_pending_generates_incrementing_handle_per_user(users_db_path):
    db.init_schema()
    uid = _make_user()
    first_handle, first_id = db.create_pending(uid, "colibre-1", "simple")
    db.mark_failed(first_id)
    second_handle, _ = db.create_pending(uid, "colibre-1", "simple")
    assert first_handle == f"abo-{uid}-1"
    assert second_handle == f"abo-{uid}-2"


def test_mark_failed_sets_status_and_keeps_handle(users_db_path):
    db.init_schema()
    uid = _make_user()
    handle, subscription_id = db.create_pending(uid, "colibre-1", "simple")
    db.mark_failed(subscription_id)
    row = db.get_current(uid)
    assert row["status"] == "failed"
    assert row["frisbii_subscription_handle"] == handle


def test_update_from_webhook_sets_status(users_db_path):
    db.init_schema()
    uid = _make_user()
    handle, _ = db.create_pending(uid, "colibre-1", "simple")
    db.update_from_webhook(handle, "trial", _future())
    row = db.get_current(uid)
    assert row["status"] == "trial"
    assert row["frisbii_subscription_handle"] == handle
    assert db.customer_known("colibre-1") is True


def test_customer_known_false_for_unknown_customer(users_db_path):
    db.init_schema()
    assert db.customer_known("colibre-inconnu") is False


def test_has_active_subscription_by_status(users_db_path):
    db.init_schema()
    uid = _make_user()
    handle, _ = db.create_pending(uid, "colibre-1", "simple")
    # pending → faux
    assert db.has_active_subscription(uid) is False
    for status in ("trial", "active"):
        db.update_from_webhook(handle, status, _future())
        assert db.has_active_subscription(uid) is True
    # cancelled futur → vrai, cancelled passé → faux
    db.update_from_webhook(handle, "cancelled", _future())
    assert db.has_active_subscription(uid) is True
    db.update_from_webhook(handle, "cancelled", _past())
    assert db.has_active_subscription(uid) is False
    db.update_from_webhook(handle, "expired", None)
    assert db.has_active_subscription(uid) is False


def test_set_cancelled(users_db_path):
    db.init_schema()
    uid = _make_user()
    handle, subscription_id = db.create_pending(uid, "colibre-1", "simple")
    db.update_from_webhook(handle, "active", _future())
    end = _future()
    db.set_cancelled(subscription_id, end)
    row = db.get_current(uid)
    assert row["status"] == "cancelled"
    assert row["current_period_end"] == end


def test_has_active_subscription_z_suffix_datetime(users_db_path):
    """Fix 2 : suffix 'Z' dans current_period_end doit être parsé correctement."""
    db.init_schema()
    uid = _make_user()
    handle, _ = db.create_pending(uid, "colibre-1", "simple")
    db.update_from_webhook(handle, "cancelled", "2099-12-31T23:59:59Z")
    assert db.has_active_subscription(uid) is True
    db.update_from_webhook(handle, "cancelled", "2020-01-01T00:00:00Z")
    assert db.has_active_subscription(uid) is False


def test_has_active_subscription_bad_datetime_returns_false(users_db_path):
    """Fix 2 : une date invalide ne doit pas lever d'exception, juste retourner False."""
    db.init_schema()
    uid = _make_user()
    handle, subscription_id = db.create_pending(uid, "colibre-1", "simple")
    # Injection directe d'une valeur invalide via update bas-niveau.
    get_conn().execute(
        "UPDATE subscriptions SET status='cancelled', current_period_end='not-a-date' "
        "WHERE id=?",
        (subscription_id,),
    )
    assert db.has_active_subscription(uid) is False


def test_trial_used_is_sticky_across_resubscribe(users_db_path):
    db.init_schema()
    uid = _make_user()
    handle, _ = db.create_pending(uid, "colibre-1", "simple")
    assert db.has_used_trial(uid) is False
    # l'abonnement entre en essai → trial_used positionné
    db.update_from_webhook(handle, "trial", _future())
    assert db.has_used_trial(uid) is True
    # essai abandonné, puis nouvelle souscription : trial_used reste vrai
    db.update_from_webhook(handle, "expired", _past())
    db.create_pending(uid, "colibre-1", "soutien")
    assert db.has_used_trial(uid) is True


def test_create_pending_initializes_subscriber_state(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "colibre-1", "simple")
    state = get_conn().execute(
        "SELECT * FROM subscriber_state WHERE user_id = ?", (uid,)
    ).fetchone()
    assert state["votes_balance"] == 0
    assert state["votes_last_credited_at"] is None


def test_credit_pending_grants_initial_two_on_first_active(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "colibre-1", "simple")
    _activate(uid, cursor_iso=None)
    balance = db.credit_pending(uid)
    assert balance == db.INITIAL_VOTES
    state = get_conn().execute(
        "SELECT votes_last_credited_at FROM subscriber_state WHERE user_id = ?",
        (uid,),
    ).fetchone()
    assert state["votes_last_credited_at"] is not None


def test_credit_pending_is_idempotent_same_day(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "colibre-1", "simple")
    _activate(uid, cursor_iso=None)
    db.credit_pending(uid)
    assert db.credit_pending(uid) == db.INITIAL_VOTES  # aucun crédit supplémentaire


def test_credit_pending_capped_at_votes_per_week(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "colibre-1", "simple")
    fifteen_days_ago = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
    _activate(uid, cursor_iso=fifteen_days_ago)
    # 15 jours = 2 semaines pleines, mais le solde est cappé à VOTES_PER_WEEK
    assert db.credit_pending(uid) == db.VOTES_PER_WEEK


def test_credit_pending_no_credit_when_not_active(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "colibre-1", "simple")  # statut 'pending'
    assert db.credit_pending(uid) == 0


def test_spend_vote_decrements_when_balance_positive(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "colibre-1", "simple")
    _activate(uid, cursor_iso=None)
    db.credit_pending(uid)  # solde = INITIAL_VOTES
    assert db.spend_vote(uid) is True
    state = get_conn().execute(
        "SELECT votes_balance FROM subscriber_state WHERE user_id = ?", (uid,)
    ).fetchone()
    assert state["votes_balance"] == db.INITIAL_VOTES - 1


def test_spend_vote_refused_when_balance_zero(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "colibre-1", "simple")
    _activate(uid, cursor_iso=None)
    # solde reste 0 tant que credit_pending n'est pas appelé
    assert db.spend_vote(uid) is False


def test_reactivation_resets_cursor_without_regranting(users_db_path):
    db.init_schema()
    uid = _make_user()
    handle, _ = db.create_pending(uid, "colibre-1", "simple")
    _activate(uid, cursor_iso=None)
    db.credit_pending(uid)  # +3, curseur posé
    # désabonnement
    db.update_from_webhook(handle, "cancelled", _future())
    # période sans abonnement simulée : on recule artificiellement le curseur
    old_cursor = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    get_conn().execute(
        "UPDATE subscriber_state SET votes_last_credited_at = ? WHERE user_id = ?",
        (old_cursor, uid),
    )
    # réabonnement
    db.update_from_webhook(handle, "active", _future())
    state = get_conn().execute(
        "SELECT votes_balance FROM subscriber_state WHERE user_id = ?", (uid,)
    ).fetchone()
    assert state["votes_balance"] == db.INITIAL_VOTES  # pas de re-crédit des +3
    # le curseur a été remis ~à maintenant → pas de crédit du gap de 30 jours
    assert db.credit_pending(uid) == db.INITIAL_VOTES


def test_trial_to_active_does_not_reset_then_grants_two(users_db_path):
    db.init_schema()
    uid = _make_user()
    handle, _ = db.create_pending(uid, "colibre-1", "simple")
    db.update_from_webhook(handle, "trial", _future())
    db.update_from_webhook(handle, "active", _future())
    # fin d'essai : credit_pending accorde les +INITIAL_VOTES initiaux
    assert db.credit_pending(uid) == db.INITIAL_VOTES
```

- [ ] **Step 3: Lancer les tests et vérifier qu'ils passent**

Run: `uv run pytest tests/subscriptions/test_db.py -v`
Expected: tous les tests passent (24 tests).

- [ ] **Step 4: Commit**

```bash
git add src/subscriptions/db.py tests/subscriptions/test_db.py
git commit -m "feat(subscriptions): historique multi-lignes + subscriber_state + handle abo-{user_id}-N"
```

---

## Task 2: `client.py` — paramètre `handle`

**Files:**

- Modify: `src/subscriptions/client.py:64-86`
- Test: `tests/subscriptions/test_client.py:28-71`

**Interfaces:**

- Consumes: rien de nouveau.
- Produces: `create_subscription_session(plan_handle: str, handle: str, accept_url: str, cancel_url: str, no_trial: bool = False, customer_handle: str | None = None, create_customer: dict | None = None) -> str`
  — nouveau paramètre positionnel `handle` en 2ᵉ position.

- [ ] **Step 1: Mettre à jour les tests existants (ils doivent échouer avec la signature actuelle)**

Dans `tests/subscriptions/test_client.py`, remplacer :

```python
def test_create_subscription_session_with_customer_handle(fake_httpx):
    fake_httpx["queue"].append(
        fake_httpx["Response"](
            200,
            {
                "hosted_page_links": {
                    "payment_info": "https://checkout.reepay.com/#/sub-1"
                }
            },
        )
    )
    url = client.create_subscription_session(
        "plan_simple",
        "https://app/ok",
        "https://app/ko",
        customer_handle="colibre-1",
    )
    assert url == "https://checkout.reepay.com/#/sub-1"
    body = fake_httpx["calls"][0]["json"]
    assert body["plan"] == "plan_simple"
    assert body["customer"] == "colibre-1"
    assert body["signup_method"] == "link"
    assert "prepare_subscription" not in body


def test_create_subscription_session_no_trial(fake_httpx):
    fake_httpx["queue"].append(
        fake_httpx["Response"](
            200,
            {
                "hosted_page_links": {
                    "payment_info": "https://checkout.reepay.com/#/sub-2"
                }
            },
        )
    )
    client.create_subscription_session(
        "plan_simple",
        "https://app/ok",
        "https://app/ko",
        no_trial=True,
        customer_handle="colibre-1",
    )
    assert fake_httpx["calls"][0]["json"]["no_trial"] is True
```

par :

```python
def test_create_subscription_session_with_customer_handle(fake_httpx):
    fake_httpx["queue"].append(
        fake_httpx["Response"](
            200,
            {
                "hosted_page_links": {
                    "payment_info": "https://checkout.reepay.com/#/sub-1"
                }
            },
        )
    )
    url = client.create_subscription_session(
        "plan_simple",
        "abo-1-1",
        "https://app/ok",
        "https://app/ko",
        customer_handle="colibre-1",
    )
    assert url == "https://checkout.reepay.com/#/sub-1"
    body = fake_httpx["calls"][0]["json"]
    assert body["plan"] == "plan_simple"
    assert body["handle"] == "abo-1-1"
    assert body["customer"] == "colibre-1"
    assert body["signup_method"] == "link"
    assert "generate_handle" not in body
    assert "prepare_subscription" not in body


def test_create_subscription_session_no_trial(fake_httpx):
    fake_httpx["queue"].append(
        fake_httpx["Response"](
            200,
            {
                "hosted_page_links": {
                    "payment_info": "https://checkout.reepay.com/#/sub-2"
                }
            },
        )
    )
    client.create_subscription_session(
        "plan_simple",
        "abo-1-2",
        "https://app/ok",
        "https://app/ko",
        no_trial=True,
        customer_handle="colibre-1",
    )
    assert fake_httpx["calls"][0]["json"]["no_trial"] is True
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_client.py -v`
Expected: FAIL (`TypeError: create_subscription_session() takes from 3 to 6 positional arguments but 4 were given` ou équivalent).

- [ ] **Step 3: Modifier `create_subscription_session`**

Dans `src/subscriptions/client.py`, remplacer :

```python
def create_subscription_session(
    plan_handle: str,
    accept_url: str,
    cancel_url: str,
    no_trial: bool = False,
    customer_handle: str | None = None,
    create_customer: dict | None = None,
) -> str:
    body: dict = {
        "plan": plan_handle,
        "signup_method": "link",
        "generate_handle": True,
        "accept_url": accept_url,
        "cancel_url": cancel_url,
    }
```

par :

```python
def create_subscription_session(
    plan_handle: str,
    handle: str,
    accept_url: str,
    cancel_url: str,
    no_trial: bool = False,
    customer_handle: str | None = None,
    create_customer: dict | None = None,
) -> str:
    body: dict = {
        "plan": plan_handle,
        "signup_method": "link",
        "handle": handle,
        "accept_url": accept_url,
        "cancel_url": cancel_url,
    }
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `uv run pytest tests/subscriptions/test_client.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/subscriptions/client.py tests/subscriptions/test_client.py
git commit -m "feat(subscriptions): create_subscription_session prend le handle en paramètre"
```

---

## Task 3: `routes.py` — `subscribe()`

**Files:**

- Modify: `src/subscriptions/routes.py:17-84`
- Test: `tests/subscriptions/test_routes.py`

**Interfaces:**

- Consumes : `db.create_pending` → `(handle, subscription_id)` (Task 1),
  `db.mark_failed(subscription_id)` (Task 1),
  `client.create_subscription_session(plan_handle, handle, ...)` (Task 2).

- [ ] **Step 1: Mettre à jour les tests de `subscribe()` dans `tests/subscriptions/test_routes.py`**

Remplacer les fonctions suivantes (en tête du fichier, après les imports et
`_sign`) :

```python
def test_subscribe_redirects_to_hosted_url(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    monkeypatch.setattr(frisbii_client, "update_customer", lambda h, d: {})
    monkeypatch.setattr(
        frisbii_client,
        "create_subscription_session",
        lambda plan,
        ok,
        ko,
        no_trial=False,
        customer_handle=None,
        create_customer=None: "https://pay.test/cs_1",
    )
    resp = client.post("/subscriptions/subscribe", data={"plan": "simple"})
    assert resp.status_code == 303
    assert resp.headers["Location"] == "https://pay.test/cs_1"
    assert db.get_by_user(uid)["status"] == "pending"


def test_subscribe_disables_trial_after_first_use(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    # L'utilisateur a déjà consommé un essai par le passé (abonnement maintenant expiré).
    db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(
        "colibre-%d" % uid, "sub_42", "trial", "2099-01-01T00:00:00+00:00"
    )
    # L'essai est terminé : abonnement expiré, trial_used reste à 1.
    db.update_from_webhook(
        "colibre-%d" % uid, "sub_42", "expired", "2020-01-01T00:00:00+00:00"
    )
    captured = {}
    monkeypatch.setattr(frisbii_client, "update_customer", lambda h, d: {})

    def fake_session(
        plan, ok, ko, no_trial=False, customer_handle=None, create_customer=None
    ):
        captured["no_trial"] = no_trial
        return "https://pay.test/cs_9"

    monkeypatch.setattr(frisbii_client, "create_subscription_session", fake_session)
    resp = client.post("/subscriptions/subscribe", data={"plan": "soutien"})
    assert resp.status_code == 303
    assert captured["no_trial"] is True


def test_subscribe_unknown_plan(logged_in_client):
    client, _ = logged_in_client
    resp = client.post("/subscriptions/subscribe", data={"plan": "bidon"})
    assert resp.status_code == 400


def test_subscribe_api_error_redirects_with_error(logged_in_client, monkeypatch):
    client, _ = logged_in_client

    def boom(h, d):
        raise frisbii_client.FrisbiiError(500, "boom")

    monkeypatch.setattr(frisbii_client, "update_customer", boom)
    resp = client.post("/subscriptions/subscribe", data={"plan": "simple"})
    assert resp.status_code == 302
    assert "error=frisbii" in resp.headers["Location"]


def test_subscribe_requires_login(sub_app):
    resp = sub_app.test_client().post(
        "/subscriptions/subscribe", data={"plan": "simple"}
    )
    assert resp.status_code in (302, 401)
```

par :

```python
def test_subscribe_redirects_to_hosted_url(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    monkeypatch.setattr(frisbii_client, "update_customer", lambda h, d: {})
    monkeypatch.setattr(
        frisbii_client,
        "create_subscription_session",
        lambda plan,
        handle,
        ok,
        ko,
        no_trial=False,
        customer_handle=None,
        create_customer=None: "https://pay.test/cs_1",
    )
    resp = client.post("/subscriptions/subscribe", data={"plan": "simple"})
    assert resp.status_code == 303
    assert resp.headers["Location"] == "https://pay.test/cs_1"
    row = db.get_current(uid)
    assert row["status"] == "pending"
    assert row["frisbii_subscription_handle"] == f"abo-{uid}-1"


def test_subscribe_disables_trial_after_first_use(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    # L'utilisateur a déjà consommé un essai par le passé (abonnement maintenant expiré).
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "trial", "2099-01-01T00:00:00+00:00")
    # L'essai est terminé : abonnement expiré, trial_used reste à 1.
    db.update_from_webhook(handle, "expired", "2020-01-01T00:00:00+00:00")
    captured = {}
    monkeypatch.setattr(frisbii_client, "update_customer", lambda h, d: {})

    def fake_session(
        plan, handle, ok, ko, no_trial=False, customer_handle=None, create_customer=None
    ):
        captured["no_trial"] = no_trial
        return "https://pay.test/cs_9"

    monkeypatch.setattr(frisbii_client, "create_subscription_session", fake_session)
    resp = client.post("/subscriptions/subscribe", data={"plan": "soutien"})
    assert resp.status_code == 303
    assert captured["no_trial"] is True


def test_subscribe_unknown_plan(logged_in_client):
    client, _ = logged_in_client
    resp = client.post("/subscriptions/subscribe", data={"plan": "bidon"})
    assert resp.status_code == 400


def test_subscribe_api_error_marks_failed_and_redirects(logged_in_client, monkeypatch):
    client, uid = logged_in_client

    def boom(h, d):
        raise frisbii_client.FrisbiiError(500, "boom")

    monkeypatch.setattr(frisbii_client, "update_customer", boom)
    resp = client.post("/subscriptions/subscribe", data={"plan": "simple"})
    assert resp.status_code == 302
    assert "error=frisbii" in resp.headers["Location"]
    row = db.get_current(uid)
    assert row["status"] == "failed"


def test_subscribe_requires_login(sub_app):
    resp = sub_app.test_client().post(
        "/subscriptions/subscribe", data={"plan": "simple"}
    )
    assert resp.status_code in (302, 401)
```

Aussi, plus bas dans le fichier, remplacer :

```python
def test_subscribe_skips_if_already_active(logged_in_client, monkeypatch):
    """Fix 1 : un abonné actif ne doit pas voir son statut remis à 'pending'."""
    client, uid = logged_in_client
    db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(
        "colibre-%d" % uid, "sub_42", "active", "2099-01-01T00:00:00+00:00"
    )
    called = []
    monkeypatch.setattr(
        frisbii_client, "update_customer", lambda h, d: called.append(h)
    )
    resp = client.post("/subscriptions/subscribe", data={"plan": "simple"})
    # Doit rediriger vers la page abonnement, sans appeler Frisbii.
    assert resp.status_code == 302
    assert "compte/abonnement" in resp.headers["Location"]
    assert called == [], "Frisbii ne doit pas être appelé pour un abonné actif"
    # Le statut DB ne doit pas avoir été écrasé.
    assert db.get_by_user(uid)["status"] == "active"


def test_subscribe_skips_if_trial_active(logged_in_client, monkeypatch):
    """Fix 1 : un abonné en période d'essai est protégé de la même façon."""
    client, uid = logged_in_client
    db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(
        "colibre-%d" % uid, "sub_42", "trial", "2099-01-01T00:00:00+00:00"
    )
    resp = client.post("/subscriptions/subscribe", data={"plan": "simple"})
    assert resp.status_code == 302
    assert "compte/abonnement" in resp.headers["Location"]
    assert db.get_by_user(uid)["status"] == "trial"
```

par :

```python
def test_subscribe_skips_if_already_active(logged_in_client, monkeypatch):
    """Fix 1 : un abonné actif ne doit pas voir son statut remis à 'pending'."""
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    called = []
    monkeypatch.setattr(
        frisbii_client, "update_customer", lambda h, d: called.append(h)
    )
    resp = client.post("/subscriptions/subscribe", data={"plan": "simple"})
    # Doit rediriger vers la page abonnement, sans appeler Frisbii.
    assert resp.status_code == 302
    assert "compte/abonnement" in resp.headers["Location"]
    assert called == [], "Frisbii ne doit pas être appelé pour un abonné actif"
    # Le statut DB ne doit pas avoir été écrasé.
    assert db.get_current(uid)["status"] == "active"


def test_subscribe_skips_if_trial_active(logged_in_client, monkeypatch):
    """Fix 1 : un abonné en période d'essai est protégé de la même façon."""
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "trial", "2099-01-01T00:00:00+00:00")
    resp = client.post("/subscriptions/subscribe", data={"plan": "simple"})
    assert resp.status_code == 302
    assert "compte/abonnement" in resp.headers["Location"]
    assert db.get_current(uid)["status"] == "trial"
```

- [ ] **Step 2: Lancer les tests concernés, vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_routes.py -k subscribe -v`
Expected: FAIL (signatures incompatibles / `db.get_by_user` n'existe plus).

- [ ] **Step 3: Réécrire `subscribe()` dans `src/subscriptions/routes.py`**

Remplacer :

```python
@subscriptions_bp.route("/subscriptions/subscribe", methods=["POST"])
@login_required
def subscribe():
    plan_key = request.form.get("plan") or ""
    handle = plans.resolve_handle(plan_key)
    if handle is None:
        return "Plan inconnu", 400

    base = os.getenv("APP_BASE_URL", "")
    if db.has_active_subscription(current_user.id):
        return redirect(f"{base}/compte/abonnement")

    cust = _customer_handle(current_user.id)
    try:
        meta = plans.plan_meta(plan_key)
        db.create_pending(
            current_user.id, cust, plan_key, meta["prix_ht"] if meta else None
        )
        no_trial = db.has_used_trial(current_user.id)
        siret = (request.form.get("siret") or "").strip()
        billing: dict = {
            "email": current_user.email,
            "first_name": request.form.get("first_name", ""),
            "last_name": request.form.get("last_name", ""),
            "address": request.form.get("address", ""),
            "city": request.form.get("city", ""),
            "postal_code": request.form.get("postal_code", ""),
            "country": request.form.get("country", "FR"),
        }
        if request.form.get("address2"):
            billing["address2"] = request.form["address2"]
        if request.form.get("company"):
            billing["company"] = request.form["company"]

        if siret:
            auth_db.set_siret(current_user.id, siret)

        customer_exists = True
        try:
            client.update_customer(cust, billing)
        except client.FrisbiiError as exc:
            if exc.status_code != 404:
                raise
            customer_exists = False

        if customer_exists:
            url = client.create_subscription_session(
                handle,
                f"{base}/compte/abonnement?paiement=succes",
                f"{base}/compte/abonnement?paiement=annule",
                customer_handle=cust,
                no_trial=no_trial,
            )
        else:
            create_customer = {"handle": cust, **billing}
            if siret:
                create_customer["metadata"] = {"siret": siret}
            url = client.create_subscription_session(
                handle,
                f"{base}/compte/abonnement?paiement=succes",
                f"{base}/compte/abonnement?paiement=annule",
                create_customer=create_customer,
                no_trial=no_trial,
            )
    except client.FrisbiiError:
        logger.exception("Échec de création de session d'abonnement Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    return redirect(url, code=303)
```

par :

```python
@subscriptions_bp.route("/subscriptions/subscribe", methods=["POST"])
@login_required
def subscribe():
    plan_key = request.form.get("plan") or ""
    plan_handle = plans.resolve_handle(plan_key)
    if plan_handle is None:
        return "Plan inconnu", 400

    base = os.getenv("APP_BASE_URL", "")
    if db.has_active_subscription(current_user.id):
        return redirect(f"{base}/compte/abonnement")

    cust = _customer_handle(current_user.id)
    meta = plans.plan_meta(plan_key)
    sub_handle, subscription_id = db.create_pending(
        current_user.id, cust, plan_key, meta["prix_ht"] if meta else None
    )
    try:
        no_trial = db.has_used_trial(current_user.id)
        siret = (request.form.get("siret") or "").strip()
        billing: dict = {
            "email": current_user.email,
            "first_name": request.form.get("first_name", ""),
            "last_name": request.form.get("last_name", ""),
            "address": request.form.get("address", ""),
            "city": request.form.get("city", ""),
            "postal_code": request.form.get("postal_code", ""),
            "country": request.form.get("country", "FR"),
        }
        if request.form.get("address2"):
            billing["address2"] = request.form["address2"]
        if request.form.get("company"):
            billing["company"] = request.form["company"]

        if siret:
            auth_db.set_siret(current_user.id, siret)

        customer_exists = True
        try:
            client.update_customer(cust, billing)
        except client.FrisbiiError as exc:
            if exc.status_code != 404:
                raise
            customer_exists = False

        if customer_exists:
            url = client.create_subscription_session(
                plan_handle,
                sub_handle,
                f"{base}/compte/abonnement?paiement=succes",
                f"{base}/compte/abonnement?paiement=annule",
                customer_handle=cust,
                no_trial=no_trial,
            )
        else:
            create_customer = {"handle": cust, **billing}
            if siret:
                create_customer["metadata"] = {"siret": siret}
            url = client.create_subscription_session(
                plan_handle,
                sub_handle,
                f"{base}/compte/abonnement?paiement=succes",
                f"{base}/compte/abonnement?paiement=annule",
                create_customer=create_customer,
                no_trial=no_trial,
            )
    except client.FrisbiiError:
        logger.exception("Échec de création de session d'abonnement Frisbii")
        db.mark_failed(subscription_id)
        return redirect("/compte/abonnement?error=frisbii")
    return redirect(url, code=303)
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `uv run pytest tests/subscriptions/test_routes.py -k subscribe -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/subscriptions/routes.py tests/subscriptions/test_routes.py
git commit -m "feat(subscriptions): subscribe() génère et transmet le handle, mark_failed en cas d'échec"
```

---

## Task 4: `routes.py` — `cancel()`, `webhook()`, `add_payment_callback()`

**Files:**

- Modify: `src/subscriptions/routes.py:104-163`
- Test: `tests/subscriptions/test_routes.py`

**Interfaces:**

- Consumes : `db.get_current` (Task 1), `db.set_cancelled(subscription_id, ...)`
  (Task 1), `db.customer_known` (Task 1), `db.update_from_webhook(subscription_handle, status, current_period_end)` (Task 1).

- [ ] **Step 1: Mettre à jour les tests concernés dans `tests/subscriptions/test_routes.py`**

Remplacer :

```python
def test_cancel_calls_api_and_marks_cancelled(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(
        "colibre-%d" % uid, "sub_42", "active", "2099-01-01T00:00:00+00:00"
    )
    monkeypatch.setattr(
        frisbii_client,
        "cancel_subscription",
        lambda handle: {"expires": "2099-02-01T00:00:00+00:00"},
    )
    resp = client.post("/subscriptions/cancel")
    assert resp.status_code == 302
    assert "resiliation=ok" in resp.headers["Location"]
    row = db.get_by_user(uid)
    assert row["status"] == "cancelled"
    assert row["current_period_end"] == "2099-02-01T00:00:00+00:00"


def test_webhook_invalid_signature(sub_app):
    resp = sub_app.test_client().post(
        "/frisbii/webhook", json={"id": "e", "signature": "x"}
    )
    assert resp.status_code == 403


def test_webhook_updates_subscription(sub_app, monkeypatch):
    from src.auth import db as auth_db

    auth_db.init_schema()
    uid = auth_db.create_user("wh@ex.fr", "hash")
    db.create_pending(uid, "colibre-%d" % uid, "simple")
    monkeypatch.setattr(
        frisbii_client,
        "get_subscription",
        lambda h: {"state": "active", "next_period_start": "2099-01-01T00:00:00+00:00"},
    )
    payload = {
        "id": "evt_1",
        "timestamp": "2026-06-25T10:00:00Z",
        "event_type": "subscription_created",
        "customer": "colibre-%d" % uid,
        "subscription": "sub_42",
    }
    payload["signature"] = _sign("s3cr3t", payload["timestamp"], payload["id"])
    resp = sub_app.test_client().post("/frisbii/webhook", json=payload)
    assert resp.status_code == 200
    row = db.get_by_user(uid)
    assert row["status"] == "active"
    assert row["frisbii_subscription_handle"] == "sub_42"
```

par :

```python
def test_cancel_calls_api_and_marks_cancelled(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    monkeypatch.setattr(
        frisbii_client,
        "cancel_subscription",
        lambda handle: {"expires": "2099-02-01T00:00:00+00:00"},
    )
    resp = client.post("/subscriptions/cancel")
    assert resp.status_code == 302
    assert "resiliation=ok" in resp.headers["Location"]
    row = db.get_current(uid)
    assert row["status"] == "cancelled"
    assert row["current_period_end"] == "2099-02-01T00:00:00+00:00"


def test_webhook_invalid_signature(sub_app):
    resp = sub_app.test_client().post(
        "/frisbii/webhook", json={"id": "e", "signature": "x"}
    )
    assert resp.status_code == 403


def test_webhook_updates_subscription(sub_app, monkeypatch):
    from src.auth import db as auth_db

    auth_db.init_schema()
    uid = auth_db.create_user("wh@ex.fr", "hash")
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    monkeypatch.setattr(
        frisbii_client,
        "get_subscription",
        lambda h: {"state": "active", "next_period_start": "2099-01-01T00:00:00+00:00"},
    )
    payload = {
        "id": "evt_1",
        "timestamp": "2026-06-25T10:00:00Z",
        "event_type": "subscription_created",
        "customer": "colibre-%d" % uid,
        "subscription": handle,
    }
    payload["signature"] = _sign("s3cr3t", payload["timestamp"], payload["id"])
    resp = sub_app.test_client().post("/frisbii/webhook", json=payload)
    assert resp.status_code == 200
    row = db.get_current(uid)
    assert row["status"] == "active"
    assert row["frisbii_subscription_handle"] == handle
```

- [ ] **Step 2: Lancer les tests concernés, vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_routes.py -k "cancel or webhook" -v`
Expected: FAIL.

- [ ] **Step 3: Réécrire `add_payment_callback()`, `cancel()` et `webhook()` dans `src/subscriptions/routes.py`**

Dans `add_payment_callback()`, remplacer :

```python
    row = db.get_by_user(current_user.id)
```

par :

```python
    row = db.get_current(current_user.id)
```

Remplacer :

```python
@subscriptions_bp.route("/subscriptions/cancel", methods=["POST"])
@login_required
def cancel():
    row = db.get_by_user(current_user.id)
    if row is None or not row["frisbii_subscription_handle"]:
        return "Aucun abonnement à résilier", 400
    try:
        sub = client.cancel_subscription(row["frisbii_subscription_handle"])
    except client.FrisbiiError:
        logger.exception("Échec de résiliation Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    db.set_cancelled(current_user.id, sub.get("expires"))
    return redirect("/compte/abonnement?resiliation=ok")


@subscriptions_bp.route("/frisbii/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(silent=True) or {}
    if not webhooks.verify_signature(payload, os.getenv("FRISBII_WEBHOOK_SECRET", "")):
        return "", 403

    customer = payload.get("customer")
    sub_handle = payload.get("subscription")
    if not customer or db.get_by_customer(customer) is None:
        return "", 200  # rien à rapprocher
    try:
        sub = client.get_subscription(sub_handle) if sub_handle else None
    except client.FrisbiiError:
        logger.exception("Webhook : lecture de l'abonnement Frisbii impossible")
        return "", 502  # Frisbii réessaiera
    if sub is None:
        return "", 200
    status, current_period_end = webhooks.map_subscription(sub)
    db.update_from_webhook(customer, sub_handle, status, current_period_end)
    return "", 200
```

par :

```python
@subscriptions_bp.route("/subscriptions/cancel", methods=["POST"])
@login_required
def cancel():
    row = db.get_current(current_user.id)
    if row is None or not row["frisbii_subscription_handle"]:
        return "Aucun abonnement à résilier", 400
    try:
        sub = client.cancel_subscription(row["frisbii_subscription_handle"])
    except client.FrisbiiError:
        logger.exception("Échec de résiliation Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    db.set_cancelled(row["id"], sub.get("expires"))
    return redirect("/compte/abonnement?resiliation=ok")


@subscriptions_bp.route("/frisbii/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(silent=True) or {}
    if not webhooks.verify_signature(payload, os.getenv("FRISBII_WEBHOOK_SECRET", "")):
        return "", 403

    customer = payload.get("customer")
    sub_handle = payload.get("subscription")
    if not customer or not db.customer_known(customer):
        return "", 200  # rien à rapprocher
    try:
        sub = client.get_subscription(sub_handle) if sub_handle else None
    except client.FrisbiiError:
        logger.exception("Webhook : lecture de l'abonnement Frisbii impossible")
        return "", 502  # Frisbii réessaiera
    if sub is None:
        return "", 200
    status, current_period_end = webhooks.map_subscription(sub)
    db.update_from_webhook(sub_handle, status, current_period_end)
    return "", 200
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `uv run pytest tests/subscriptions/test_routes.py -v`
Expected: PASS (tous les tests du fichier, 11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/subscriptions/routes.py tests/subscriptions/test_routes.py
git commit -m "feat(subscriptions): cancel/webhook/add_payment_callback sur get_current et customer_known"
```

---

## Task 5: `compte_abonnement.py` — statut `failed` ne bloque plus la souscription

**Files:**

- Modify: `src/pages/compte_abonnement.py:297-321`
- Test: `tests/subscriptions/test_compte_abonnement.py`

**Interfaces:**

- Consumes : `db.get_current` (Task 1).
- Produces : `_show_active_view(row) -> bool` (utilisée par `layout()`).

- [ ] **Step 1: Écrire les tests (ils échoueront : `_show_active_view` n'existe pas encore)**

Ajouter à la fin de `tests/subscriptions/test_compte_abonnement.py` :

```python
def test_show_active_view_true_for_live_statuses(monkeypatch):
    from src.pages import compte_abonnement

    for status in ("pending", "trial", "active", "cancelled", "expired"):
        assert compte_abonnement._show_active_view({"status": status}) is True


def test_show_active_view_false_for_failed_or_none(monkeypatch):
    from src.pages import compte_abonnement

    assert compte_abonnement._show_active_view({"status": "failed"}) is False
    assert compte_abonnement._show_active_view(None) is False
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: FAIL (`AttributeError: module 'src.pages.compte_abonnement' has no attribute '_show_active_view'`).

- [ ] **Step 3: Ajouter `_show_active_view` et l'utiliser dans `layout()`**

Dans `src/pages/compte_abonnement.py`, juste avant `def layout(**query):`, ajouter :

```python
def _show_active_view(row) -> bool:
    return row is not None and row["status"] != "failed"


```

Puis remplacer, dans `layout()` :

```python
    row = db.get_by_user(current_user.id) if current_user.is_authenticated else None
    trial_used = (
        db.has_used_trial(current_user.id) if current_user.is_authenticated else False
    )

    body = [html.H2("Abonnement", className="mb-4")]
    banner = _tous_abonnes_banner()
    if banner is not None:
        body.append(banner)
    body.extend(_feedback(query))

    if row is not None:
        body.append(_active_view(row))
        body.append(_resiliation_modal(row["current_period_end"]))
    else:
        body.extend([_plan_cards(trial_used=trial_used), _explainer()])
```

par :

```python
    row = db.get_current(current_user.id) if current_user.is_authenticated else None
    trial_used = (
        db.has_used_trial(current_user.id) if current_user.is_authenticated else False
    )

    body = [html.H2("Abonnement", className="mb-4")]
    banner = _tous_abonnes_banner()
    if banner is not None:
        body.append(banner)
    body.extend(_feedback(query))

    if _show_active_view(row):
        body.append(_active_view(row))
        body.append(_resiliation_modal(row["current_period_end"]))
    else:
        body.extend([_plan_cards(trial_used=trial_used), _explainer()])
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pages/compte_abonnement.py tests/subscriptions/test_compte_abonnement.py
git commit -m "fix(subscriptions): un abonnement en échec (failed) ne bloque plus le réabonnement"
```

---

## Task 6: Vérification finale

**Files:** aucun changement, exécution seule.

- [ ] **Step 1: Lancer toute la suite de tests**

Run: `uv run pytest`
Expected: tous les tests passent (aucune régression sur les autres modules —
`compte_roadmap.py`, `_compte_shell.py`, `auth/routes.py` n'appellent que
`credit_pending`/`next_recharge_at`/`spend_vote`/`has_active_subscription`,
dont les signatures n'ont pas changé).

- [ ] **Step 2: Vérifier qu'aucune référence à l'ancienne API ne subsiste**

Run: `grep -rn "get_by_user\|get_by_customer" src/ tests/ --include=*.py`
Expected: aucune occurrence (en dehors, éventuellement, de code non lié à
`subscriptions` qui définirait une fonction homonyme dans un autre module —
vérifier au cas par cas si le grep remonte autre chose que
`src/subscriptions/` ou `tests/subscriptions/`).

- [ ] **Step 3: Commit final si des ajustements ont été nécessaires**

```bash
git add -A
git status
# Si des fichiers sont en attente suite à des corrections des steps
# précédents :
git commit -m "chore(subscriptions): vérification finale historique + handle abo"
```
