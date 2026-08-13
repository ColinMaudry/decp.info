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


def _set_votes_cursor(uid, days_ago):
    """Recule le curseur d'accumulation pour simuler le temps écoulé."""
    cursor = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    get_conn().execute(
        "UPDATE subscriber_state SET votes_last_credited_at = ? WHERE user_id = ?",
        (cursor, uid),
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


def test_update_from_webhook_active_sets_status_and_period_end(users_db_path):
    """Le retrait de l'écriture `trial_used` ne doit pas casser le reste de
    `update_from_webhook` : statut et `current_period_end` continuent d'être
    mis à jour pour un webhook faisant passer un abonnement à 'active'."""
    db.init_schema()
    uid = _make_user()
    handle, _ = db.create_pending(uid, "colibre-1", "simple")
    end = _future()
    db.update_from_webhook(handle, "active", end)
    row = db.get_current(uid)
    assert row["status"] == "active"
    assert row["current_period_end"] == end


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


def test_has_active_subscription_naive_datetime_treated_as_utc(users_db_path):
    """Revue #132 : une valeur naïve (saisie à la main, via l'admin par ex.)
    ne doit pas lever de TypeError à la comparaison avec un datetime aware."""
    db.init_schema()
    uid = _make_user()
    handle, subscription_id = db.create_pending(uid, "colibre-1", "simple")
    future_naive = (datetime.now() + timedelta(days=2)).isoformat()
    get_conn().execute(
        "UPDATE subscriptions SET status='cancelled', current_period_end=? WHERE id=?",
        (future_naive, subscription_id),
    )
    assert db.has_active_subscription(uid) is True
    past_naive = (datetime.now() - timedelta(days=2)).isoformat()
    get_conn().execute(
        "UPDATE subscriptions SET current_period_end=? WHERE id=?",
        (past_naive, subscription_id),
    )
    assert db.has_active_subscription(uid) is False


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


def test_credit_pending_no_credit_without_subscription_row(users_db_path):
    db.init_schema()
    uid = _make_user()
    # jamais passé par create_pending : aucune ligne subscriptions ni subscriber_state
    assert db.credit_pending(uid) == 0
    assert db.get_subscriber_state(uid) is None  # aucune ligne créée au passage


def test_credit_pending_tous_abonnes_credits_without_subscription_row(
    users_db_path, monkeypatch
):
    db.init_schema()
    uid = _make_user()
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    assert db.get_current(uid) is None  # jamais souscrit
    assert db.credit_pending(uid) == db.INITIAL_VOTES
    state = db.get_subscriber_state(uid)
    assert state["votes_balance"] == db.INITIAL_VOTES
    assert state["votes_last_credited_at"] is not None


def test_credit_pending_tous_abonnes_is_idempotent_same_day(users_db_path, monkeypatch):
    db.init_schema()
    uid = _make_user()
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    db.credit_pending(uid)
    assert db.credit_pending(uid) == db.INITIAL_VOTES  # aucun crédit supplémentaire


def test_credit_pending_tous_abonnes_recharges_after_a_week(users_db_path, monkeypatch):
    """Le solde d'un accès gratuit se recharge chaque semaine, comme un abonné."""
    db.init_schema()
    uid = _make_user()
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    db.credit_pending(uid)
    assert db.spend_vote(uid) is True
    assert db.spend_vote(uid) is True
    assert db.credit_pending(uid) == db.INITIAL_VOTES - 2  # pas encore de recharge
    _set_votes_cursor(uid, days_ago=8)
    assert db.credit_pending(uid) == db.VOTES_PER_WEEK


def test_credit_pending_tous_abonnes_capped_at_votes_per_week(
    users_db_path, monkeypatch
):
    db.init_schema()
    uid = _make_user()
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    db.credit_pending(uid)
    # 3 semaines d'absence ne cumulent pas : le solde reste plafonné
    _set_votes_cursor(uid, days_ago=21)
    assert db.credit_pending(uid) == db.VOTES_PER_WEEK


def test_next_recharge_at_set_for_tous_abonnes_user(users_db_path, monkeypatch):
    db.init_schema()
    uid = _make_user()
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    assert db.next_recharge_at(uid) is None  # curseur pas encore posé
    db.credit_pending(uid)
    assert db.next_recharge_at(uid) is not None


def test_cancelled_within_period_keeps_accruing(users_db_path):
    """Désabonné en cours de période : il a payé, il continue d'accumuler.

    Sans ce comportement, `credit_pending` sortait avant de faire avancer le
    curseur et la page roadmap annonçait un rechargement déjà passé.
    """
    db.init_schema()
    uid = _make_user()
    handle, _ = db.create_pending(uid, "colibre-1", "simple")
    _activate(uid, cursor_iso=None)
    db.credit_pending(uid)  # pose le curseur
    # désabonnement, accès conservé jusqu'à la fin de période
    end = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    db.update_from_webhook(handle, "cancelled", end)
    assert db.has_active_subscription(uid) is True
    _set_votes_cursor(uid, days_ago=17)  # deux semaines pleines écoulées
    assert db.credit_pending(uid) == db.VOTES_PER_WEEK
    nxt = db.next_recharge_at(uid)
    assert nxt is not None
    assert nxt > datetime.now(timezone.utc)


def test_next_recharge_at_none_when_subscription_ends_first(users_db_path):
    """Désabonnement qui expire avant l'échéance : aucun rechargement à annoncer."""
    db.init_schema()
    uid = _make_user()
    handle, _ = db.create_pending(uid, "colibre-1", "simple")
    _activate(uid, cursor_iso=None)
    db.credit_pending(uid)  # curseur ~maintenant, échéance dans 7 jours
    db.update_from_webhook(
        handle,
        "cancelled",
        (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
    )
    assert db.has_active_subscription(uid) is True  # accès encore ouvert
    assert db.next_recharge_at(uid) is None


def test_next_recharge_at_none_after_period_end(users_db_path):
    """Abonnement expiré : plus d'accès, plus d'accumulation, pas de date."""
    db.init_schema()
    uid = _make_user()
    handle, _ = db.create_pending(uid, "colibre-1", "simple")
    _activate(uid, cursor_iso=None)
    db.credit_pending(uid)
    db.update_from_webhook(handle, "cancelled", _past())
    assert db.has_active_subscription(uid) is False
    _set_votes_cursor(uid, days_ago=17)
    assert db.credit_pending(uid) == db.INITIAL_VOTES  # solde figé
    assert db.next_recharge_at(uid) is None


def test_next_recharge_at_none_during_trial(users_db_path):
    """Période d'essai (#132) : aucune ligne `subscriptions` n'existe tant que
    l'essai n'a pas débouché sur une souscription, donc aucun vote n'a encore
    été crédité et aucune date de rechargement n'est à annoncer."""
    db.init_schema()
    uid = _make_user()
    db.start_trial_if_new(uid)
    assert db.get_current(uid) is None
    assert db.next_recharge_at(uid) is None


def test_next_recharge_at_in_future_for_active_subscriber(users_db_path):
    """Abonné actif : la date annoncée est toujours à venir, jamais dans le passé."""
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "colibre-1", "simple")
    _activate(uid, cursor_iso=None)
    db.credit_pending(uid)
    _set_votes_cursor(uid, days_ago=17)  # deux semaines pleines non créditées
    db.credit_pending(uid)
    nxt = db.next_recharge_at(uid)
    assert nxt is not None
    assert nxt > datetime.now(timezone.utc)


def test_spend_vote_works_under_tous_abonnes_without_subscription_row(
    users_db_path, monkeypatch
):
    db.init_schema()
    uid = _make_user()
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    db.credit_pending(uid)
    assert db.spend_vote(uid) is True


def test_credit_pending_tolerates_unknown_user_under_tous_abonnes(
    users_db_path, monkeypatch
):
    """user_id absent de `users` : renvoie 0 sans lever d'IntegrityError (FK)."""
    db.init_schema()
    _make_user()  # garantit que la table users existe
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    assert db.credit_pending(999999) == 0


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


def test_pending_to_active_via_webhook_grants_initial_votes(users_db_path):
    """Souscription directe (#132) : `pending` → `active` par webhook accorde
    les +INITIAL_VOTES initiaux, comme n'importe quelle première activation.

    Distinct de `test_credit_pending_grants_initial_two_on_first_active`, qui
    active la ligne par UPDATE SQL direct plutôt que par
    `update_from_webhook` : celui-ci couvre en plus le passage par
    `freeze_votes_cursor` déclenché par la transition webhook elle-même."""
    db.init_schema()
    uid = _make_user()
    handle, _ = db.create_pending(uid, "colibre-1", "simple")
    db.update_from_webhook(handle, "active", _future())
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


def test_evenement_emis_sur_trial_vers_active(users_db_path, monkeypatch):
    db.init_schema()
    uid = _make_user()
    appels = []
    monkeypatch.setattr(
        db.tracking,
        "track_subscription_goal",
        lambda action, plan=None, revenue=None: appels.append((action, plan, revenue)),
    )

    handle, _sub_id = db.create_pending(uid, "cust-1", "simple", 20)
    db.update_from_webhook(handle, "trial", "2026-08-05T00:00:00Z")
    appels.clear()

    db.update_from_webhook(handle, "active", "2026-09-05T00:00:00Z")

    assert appels == [("subscription_active", "simple", 20)]


def test_evenement_emis_sur_pending_vers_active(users_db_path, monkeypatch):
    """Souscription directe sans essai (no_trial) : même événement."""
    db.init_schema()
    uid = _make_user()
    appels = []
    monkeypatch.setattr(
        db.tracking,
        "track_subscription_goal",
        lambda action, plan=None, revenue=None: appels.append((action, plan, revenue)),
    )

    handle, _ = db.create_pending(uid, "cust-2", "soutien", 50)
    db.update_from_webhook(handle, "active", "2026-09-05T00:00:00Z")

    assert appels == [("subscription_active", "soutien", 50)]


def test_pas_d_evenement_sur_redelivrance(users_db_path, monkeypatch):
    """Frisbii peut redélivrer un webhook : pas de double comptage."""
    db.init_schema()
    uid = _make_user()
    appels = []
    monkeypatch.setattr(
        db.tracking,
        "track_subscription_goal",
        lambda action, plan=None, revenue=None: appels.append(action),
    )

    handle, _ = db.create_pending(uid, "cust-3", "simple", 20)
    db.update_from_webhook(handle, "active", "2026-09-05T00:00:00Z")
    db.update_from_webhook(handle, "active", "2026-09-05T00:00:00Z")

    assert appels == ["subscription_active"]


def test_pas_d_evenement_sur_annulation(users_db_path, monkeypatch):
    db.init_schema()
    uid = _make_user()
    appels = []
    monkeypatch.setattr(
        db.tracking,
        "track_subscription_goal",
        lambda action, plan=None, revenue=None: appels.append(action),
    )

    handle, _ = db.create_pending(uid, "cust-4", "simple", 20)
    db.update_from_webhook(handle, "trial", "2026-08-05T00:00:00Z")
    db.update_from_webhook(handle, "cancelled", "2026-08-05T00:00:00Z")

    assert appels == []


def test_start_trial_if_new_creates_state_with_trial_ends_at_in_two_days(
    users_db_path,
):
    db.init_schema()
    uid = _make_user()
    assert db.get_subscriber_state(uid) is None

    db.start_trial_if_new(uid)

    state = db.get_subscriber_state(uid)
    assert state is not None
    ends = datetime.fromisoformat(state["trial_ends_at"])
    expected = datetime.now(timezone.utc) + timedelta(days=db.TRIAL_DAYS)
    assert abs((ends - expected).total_seconds()) < 5


def test_start_trial_if_new_is_idempotent(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.start_trial_if_new(uid)
    first = db.get_subscriber_state(uid)["trial_ends_at"]

    db.start_trial_if_new(uid)

    second = db.get_subscriber_state(uid)["trial_ends_at"]
    assert second == first


def test_start_trial_if_new_unknown_user_does_not_insert_or_raise(users_db_path):
    db.init_schema()
    _make_user()  # garantit que la table users existe

    db.start_trial_if_new(999999)

    assert db.get_subscriber_state(999999) is None


def test_trial_active_true_for_future_end(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.start_trial_if_new(uid)
    assert db.trial_active(uid) is True


def test_trial_active_false_for_past_end(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.start_trial_if_new(uid)
    get_conn().execute(
        "UPDATE subscriber_state SET trial_ends_at = ? WHERE user_id = ?",
        (_past(), uid),
    )
    assert db.trial_active(uid) is False


def test_trial_active_false_when_trial_ends_at_is_null(users_db_path):
    db.init_schema()
    uid = _make_user()
    get_conn().execute(
        "INSERT INTO subscriber_state (user_id, updated_at) VALUES (?, ?)",
        (uid, datetime.now(timezone.utc).isoformat()),
    )
    assert db.trial_active(uid) is False


def test_trial_active_false_when_no_subscriber_state_row(users_db_path):
    db.init_schema()
    uid = _make_user()
    assert db.get_subscriber_state(uid) is None
    assert db.trial_active(uid) is False


def test_trial_active_tolerates_z_suffix(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.start_trial_if_new(uid)
    get_conn().execute(
        "UPDATE subscriber_state SET trial_ends_at = ? WHERE user_id = ?",
        ("2099-12-31T23:59:59Z", uid),
    )
    assert db.trial_active(uid) is True


def test_trial_active_false_on_unparsable_datetime(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.start_trial_if_new(uid)
    get_conn().execute(
        "UPDATE subscriber_state SET trial_ends_at = ? WHERE user_id = ?",
        ("not-a-date", uid),
    )
    assert db.trial_active(uid) is False


def test_trial_active_naive_datetime_treated_as_utc(users_db_path):
    """Revue #132 : une valeur naïve (saisie à la main, via l'admin par ex.)
    ne doit pas lever de TypeError à la comparaison avec un datetime aware."""
    db.init_schema()
    uid = _make_user()
    db.start_trial_if_new(uid)
    future_naive = (datetime.now() + timedelta(days=2)).isoformat()
    get_conn().execute(
        "UPDATE subscriber_state SET trial_ends_at = ? WHERE user_id = ?",
        (future_naive, uid),
    )
    assert db.trial_active(uid) is True

    past_naive = (datetime.now() - timedelta(days=2)).isoformat()
    get_conn().execute(
        "UPDATE subscriber_state SET trial_ends_at = ? WHERE user_id = ?",
        (past_naive, uid),
    )
    assert db.trial_active(uid) is False


def test_has_access_true_during_trial_without_subscriptions_row(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.start_trial_if_new(uid)
    assert db.get_current(uid) is None
    assert db.has_access(uid) is True


def test_has_access_true_for_active_subscriber_with_expired_trial(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.start_trial_if_new(uid)
    get_conn().execute(
        "UPDATE subscriber_state SET trial_ends_at = ? WHERE user_id = ?",
        (_past(), uid),
    )
    handle, _ = db.create_pending(uid, "colibre-1", "simple")
    db.update_from_webhook(handle, "active", _future())
    assert db.trial_active(uid) is False
    assert db.has_access(uid) is True


def test_has_access_false_without_trial_or_subscription(users_db_path):
    db.init_schema()
    uid = _make_user()
    assert db.has_access(uid) is False


def test_has_active_subscription_false_during_trial_alone(users_db_path):
    """Garde-fou : l'essai ne doit jamais faire basculer has_active_subscription."""
    db.init_schema()
    uid = _make_user()
    db.start_trial_if_new(uid)
    assert db.trial_active(uid) is True
    assert db.has_active_subscription(uid) is False
