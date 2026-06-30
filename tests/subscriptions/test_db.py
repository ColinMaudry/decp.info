from datetime import datetime, timedelta, timezone

from src.auth import db as auth_db
from src.subscriptions import db


def _future():
    return (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()


def _past():
    return (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def test_init_schema_creates_table(users_db_path):
    db.init_schema()
    conn = auth_db.get_conn()
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "subscriptions" in tables


def test_create_pending_and_get_by_user(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    row = db.get_by_user(uid)
    assert row["status"] == "pending"
    assert row["plan"] == "simple"
    assert row["frisbii_customer_handle"] == "decpinfo-1"


def test_update_from_webhook_sets_status_and_handle(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    db.update_from_webhook("decpinfo-1", "sub_42", "trial", _future())
    row = db.get_by_user(uid)
    assert row["status"] == "trial"
    assert row["frisbii_subscription_handle"] == "sub_42"
    assert db.get_by_customer("decpinfo-1")["user_id"] == uid


def test_has_active_subscription_by_status(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    # pending → faux
    assert db.has_active_subscription(uid) is False
    for status in ("trial", "active"):
        db.update_from_webhook("decpinfo-1", "sub_42", status, _future())
        assert db.has_active_subscription(uid) is True
    # cancelled futur → vrai, cancelled passé → faux
    db.update_from_webhook("decpinfo-1", "sub_42", "cancelled", _future())
    assert db.has_active_subscription(uid) is True
    db.update_from_webhook("decpinfo-1", "sub_42", "cancelled", _past())
    assert db.has_active_subscription(uid) is False
    db.update_from_webhook("decpinfo-1", "sub_42", "expired", None)
    assert db.has_active_subscription(uid) is False


def test_set_cancelled(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    db.update_from_webhook("decpinfo-1", "sub_42", "active", _future())
    end = _future()
    db.set_cancelled(uid, end)
    row = db.get_by_user(uid)
    assert row["status"] == "cancelled"
    assert row["current_period_end"] == end


def test_has_active_subscription_z_suffix_datetime(users_db_path):
    """Fix 2 : suffix 'Z' dans current_period_end doit être parsé correctement."""
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    # Frisbii peut renvoyer des dates avec 'Z' au lieu de '+00:00'.
    db.update_from_webhook("decpinfo-1", "sub_42", "cancelled", "2099-12-31T23:59:59Z")
    assert db.has_active_subscription(uid) is True
    db.update_from_webhook("decpinfo-1", "sub_42", "cancelled", "2020-01-01T00:00:00Z")
    assert db.has_active_subscription(uid) is False


def test_has_active_subscription_bad_datetime_returns_false(users_db_path):
    """Fix 2 : une date invalide ne doit pas lever d'exception, juste retourner False."""
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    # Injection directe d'une valeur invalide via update bas-niveau.
    from src.auth.db import get_conn

    get_conn().execute(
        "UPDATE subscriptions SET status='cancelled', current_period_end='not-a-date' "
        "WHERE user_id=?",
        (uid,),
    )
    assert db.has_active_subscription(uid) is False


def test_trial_used_is_sticky_across_resubscribe(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    assert db.has_used_trial(uid) is False
    # l'abonnement entre en essai → trial_used positionné
    db.update_from_webhook("decpinfo-1", "sub_42", "trial", _future())
    assert db.has_used_trial(uid) is True
    # essai abandonné, puis nouvelle souscription : trial_used reste vrai
    db.update_from_webhook("decpinfo-1", "sub_42", "expired", _past())
    db.create_pending(uid, "decpinfo-1", "soutien")
    assert db.has_used_trial(uid) is True


def test_init_schema_creates_votes_columns(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    row = db.get_by_user(uid)
    assert row["votes_balance"] == 0
    assert row["votes_credited_until"] is None
