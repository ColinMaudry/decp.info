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
    conn.execute("DROP TABLE IF EXISTS subscriptions")
    conn.execute("DROP TABLE IF EXISTS subscriber_state")
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
    assert handle == "colibre-1-1"
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
    assert first_handle == "colibre-1-1"
    assert second_handle == "colibre-1-2"


def test_create_pending_isole_les_compteurs_par_environnement(users_db_path):
    """Un handle d'un autre environnement ne décale pas la numérotation (#126)."""
    db.init_schema()
    uid = _make_user()
    prod_handle, _ = db.create_pending(uid, f"colibre-{uid}", "simple")
    test_handle, _ = db.create_pending(uid, f"colibre_test-{uid}", "simple")
    assert prod_handle == f"colibre-{uid}-1"
    assert test_handle == f"colibre_test-{uid}-1"


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
    state = (
        get_conn()
        .execute("SELECT * FROM subscriber_state WHERE user_id = ?", (uid,))
        .fetchone()
    )
    assert state["votes_balance"] == 0
    assert state["votes_last_credited_at"] is None


def test_credit_pending_grants_initial_two_on_first_active(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "colibre-1", "simple")
    _activate(uid, cursor_iso=None)
    balance = db.credit_pending(uid)
    assert balance == db.INITIAL_VOTES
    state = (
        get_conn()
        .execute(
            "SELECT votes_last_credited_at FROM subscriber_state WHERE user_id = ?",
            (uid,),
        )
        .fetchone()
    )
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
    state = (
        get_conn()
        .execute("SELECT votes_balance FROM subscriber_state WHERE user_id = ?", (uid,))
        .fetchone()
    )
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
    state = (
        get_conn()
        .execute("SELECT votes_balance FROM subscriber_state WHERE user_id = ?", (uid,))
        .fetchone()
    )
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


def test_list_by_user_returns_most_recent_first(users_db_path):
    uid = _make_user()
    db.init_schema()
    _handle1, sub_id1 = db.create_pending(uid, "cust-1", "simple")
    _handle2, sub_id2 = db.create_pending(uid, "cust-1", "soutien")

    rows = db.list_by_user(uid)

    assert [r["id"] for r in rows] == [sub_id2, sub_id1]


def test_set_status_updates_status(users_db_path):
    uid = _make_user()
    db.init_schema()
    _handle, sub_id = db.create_pending(uid, "cust-1", "simple")

    db.set_status(sub_id, "active")

    row = db.get_current(uid)
    assert row["status"] == "active"


def test_get_subscriber_state_returns_row_after_create_pending(users_db_path):
    uid = _make_user()
    db.init_schema()
    db.create_pending(uid, "cust-1", "simple")

    state = db.get_subscriber_state(uid)

    assert state is not None
    assert state["user_id"] == uid


def test_get_subscriber_state_returns_none_for_unknown_user(users_db_path):
    db.init_schema()
    assert db.get_subscriber_state(999999) is None


def test_subscription_statuses_constant():
    assert db.SUBSCRIPTION_STATUSES == (
        "active",
        "trial",
        "cancelled",
        "expired",
        "pending",
    )
