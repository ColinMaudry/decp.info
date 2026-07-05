import hashlib
import hmac

from src.subscriptions import client as frisbii_client
from src.subscriptions import db


def _sign(secret, timestamp, event_id):
    return hmac.new(
        secret.encode(), (timestamp + event_id).encode(), hashlib.sha256
    ).hexdigest()


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


def test_change_payment_method_redirects_to_hosted_url(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    monkeypatch.setattr(
        frisbii_client,
        "get_payment_info_url",
        lambda h,
        accept_url,
        cancel_url: f"https://pay.test/{h}?a={accept_url}&c={cancel_url}",
    )
    resp = client.post("/subscriptions/change-payment-method")
    assert resp.status_code == 303
    assert resp.headers["Location"].startswith(f"https://pay.test/{handle}")
    assert (
        "carte%3Dsucces" in resp.headers["Location"]
        or "carte=succes" in resp.headers["Location"]
    )
    assert (
        "carte%3Dannule" in resp.headers["Location"]
        or "carte=annule" in resp.headers["Location"]
    )


def test_change_payment_method_without_subscription(logged_in_client):
    client, _ = logged_in_client
    resp = client.post("/subscriptions/change-payment-method")
    assert resp.status_code == 400


def test_change_payment_method_api_error_redirects(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")

    def boom(h, accept_url, cancel_url):
        raise frisbii_client.FrisbiiError(500, "boom")

    monkeypatch.setattr(frisbii_client, "get_payment_info_url", boom)
    resp = client.post("/subscriptions/change-payment-method")
    assert resp.status_code == 302
    assert "error=frisbii" in resp.headers["Location"]


def test_change_payment_method_requires_login(sub_app):
    resp = sub_app.test_client().post("/subscriptions/change-payment-method")
    assert resp.status_code in (302, 401)


def test_update_changes_plan_and_redirects(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    monkeypatch.setattr(frisbii_client, "update_customer", lambda h, d: {})
    captured = {}

    def fake_change(sub_handle, plan_handle, timing="renewal"):
        captured.update(sub_handle=sub_handle, plan_handle=plan_handle, timing=timing)
        return {}

    monkeypatch.setattr(frisbii_client, "change_subscription", fake_change)
    resp = client.post("/subscriptions/update", data={"plan": "soutien"})
    assert resp.status_code == 303
    assert "maj=succes" in resp.headers["Location"]
    assert captured["sub_handle"] == handle
    assert captured["plan_handle"] == "plan_soutien"
    assert captured["timing"] == "renewal"


def test_update_pending_uses_immediate_timing(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    monkeypatch.setattr(frisbii_client, "update_customer", lambda h, d: {})
    captured = {}
    monkeypatch.setattr(
        frisbii_client,
        "change_subscription",
        lambda sub_handle, plan_handle, timing="renewal": captured.update(
            timing=timing
        ),
    )
    resp = client.post("/subscriptions/update", data={"plan": "soutien"})
    assert resp.status_code == 303
    assert captured["timing"] == "immediate"


def test_update_same_plan_skips_change_subscription(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    called = []
    monkeypatch.setattr(frisbii_client, "update_customer", lambda h, d: {})
    monkeypatch.setattr(
        frisbii_client,
        "change_subscription",
        lambda *a, **k: called.append(a),
    )
    resp = client.post("/subscriptions/update", data={"plan": "simple"})
    assert resp.status_code == 303
    assert "maj=succes" in resp.headers["Location"]
    assert called == [], (
        "formule inchangée : change_subscription ne doit pas être appelé"
    )


def test_update_without_subscription_returns_400(logged_in_client):
    client, _ = logged_in_client
    resp = client.post("/subscriptions/update", data={"plan": "simple"})
    assert resp.status_code == 400


def test_update_unknown_plan_returns_400(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    resp = client.post("/subscriptions/update", data={"plan": "bidon"})
    assert resp.status_code == 400


def test_update_api_error_redirects(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")

    def boom(h, d):
        raise frisbii_client.FrisbiiError(500, "boom")

    monkeypatch.setattr(frisbii_client, "update_customer", boom)
    resp = client.post("/subscriptions/update", data={"plan": "soutien"})
    assert resp.status_code == 302
    assert "error=frisbii" in resp.headers["Location"]


def test_update_requires_login(sub_app):
    resp = sub_app.test_client().post("/subscriptions/update", data={"plan": "simple"})
    assert resp.status_code in (302, 401)
