import hashlib
import hmac

import pytest

from src.subscriptions import client as frisbii_client
from src.subscriptions import db


def _sign(secret, timestamp, event_id):
    return hmac.new(
        secret.encode(), (timestamp + event_id).encode(), hashlib.sha256
    ).hexdigest()


@pytest.fixture
def capture_accept(monkeypatch):
    """Intercepte l'URL d'acceptation transmise à Frisbii."""
    captured = {}

    def fake_session(plan_handle, handle, accept_url, cancel_url, **kwargs):
        captured["accept_url"] = accept_url
        captured["no_trial"] = kwargs.get("no_trial")
        return "https://checkout.example/session"

    monkeypatch.setattr(frisbii_client, "create_subscription_session", fake_session)
    monkeypatch.setattr(frisbii_client, "update_customer", lambda handle, data: {})
    return captured


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
        create_customer=None: ("https://pay.test/cs_1"),
    )
    resp = client.post("/subscriptions/subscribe", data={"plan": "simple"})
    assert resp.status_code == 303
    assert resp.headers["Location"] == "https://pay.test/cs_1"
    row = db.get_current(uid)
    assert row["status"] == "pending"
    # APP_BASE_URL=http://localhost:8050 dans la fixture → préfixe colibre_dev (#126)
    assert row["frisbii_customer_handle"] == f"colibre_dev-{uid}"
    assert row["frisbii_subscription_handle"] == f"colibre_dev-{uid}-1"


def test_subscribe_sends_no_trial_true_in_frisbii_request_body(
    logged_in_client, fake_httpx
):
    """L'essai n'existe plus côté Frisbii (#132) : le corps JSON envoyé à
    POST /v1/subscription porte `no_trial: True`, y compris pour un
    utilisateur qui n'a jamais souscrit auparavant (le cas qui bénéficiait
    autrefois d'un essai). On inspecte le corps réellement capturé par
    `fake_httpx`, pas seulement le code de retour côté colibre."""
    test_client, uid = logged_in_client
    assert db.get_current(uid) is None  # jamais souscrit auparavant
    Response = fake_httpx["Response"]
    fake_httpx["queue"].extend(
        [
            Response(200, {}),  # PUT /v1/customer/{handle}
            Response(200, {}),  # POST /v1/subscription
            Response(200, {"url": "https://checkout.example/session"}),
        ]
    )

    resp = test_client.post("/subscriptions/subscribe", data={"plan": "simple"})

    assert resp.status_code == 303
    create_calls = [
        c for c in fake_httpx["calls"] if c["url"].endswith("/v1/subscription")
    ]
    assert len(create_calls) == 1
    assert create_calls[0]["json"]["no_trial"] is True


def test_accept_url_has_no_trial_discriminant(logged_in_client, capture_accept):
    """L'essai n'existe plus côté Frisbii (#132) : l'URL de retour du checkout
    ne porte donc plus aucun discriminant d'essai (`souscription=trial`),
    toute souscription étant immédiatement payante."""
    test_client, _ = logged_in_client

    test_client.post("/subscriptions/subscribe", data={"plan": "simple"})

    assert "accept_url" in capture_accept
    assert "paiement=succes" in capture_accept["accept_url"]
    assert "souscription=trial" not in capture_accept["accept_url"]
    assert capture_accept["no_trial"] is True


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


def test_reactivate_calls_api_and_marks_active(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    db.set_cancelled(db.get_current(uid)["id"], "2099-02-01T00:00:00+00:00")
    monkeypatch.setattr(
        frisbii_client,
        "uncancel_subscription",
        lambda handle: {
            "state": "active",
            "next_period_start": "2099-03-01T00:00:00+00:00",
        },
    )
    resp = client.post("/subscriptions/reactivate")
    assert resp.status_code == 302
    assert "reactivation=ok" in resp.headers["Location"]
    row = db.get_current(uid)
    assert row["status"] == "active"
    assert row["current_period_end"] == "2099-03-01T00:00:00+00:00"


def test_reactivate_requires_cancelled_subscription(logged_in_client):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    resp = client.post("/subscriptions/reactivate")
    assert resp.status_code == 400


def test_reactivate_rejects_already_expired_period(logged_in_client, monkeypatch):
    """Un statut "cancelled" dont current_period_end est déjà dépassé (webhook
    "expired" en retard ou perdu) n'a plus d'accès en cours : la réactivation
    doit être refusée, sinon set_reactivated repasserait "active" sans combler
    la coupure d'accès (pas de freeze_votes_cursor dans ce chemin)."""
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    db.set_cancelled(db.get_current(uid)["id"], "2020-01-01T00:00:00+00:00")
    resp = client.post("/subscriptions/reactivate")
    assert resp.status_code == 400
    assert db.get_current(uid)["status"] == "cancelled"


def test_reactivate_api_error_redirects(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    db.set_cancelled(db.get_current(uid)["id"], "2099-02-01T00:00:00+00:00")

    def boom(handle):
        raise frisbii_client.FrisbiiError(500, "boom")

    monkeypatch.setattr(frisbii_client, "uncancel_subscription", boom)
    resp = client.post("/subscriptions/reactivate")
    assert resp.status_code == 302
    assert "error=frisbii" in resp.headers["Location"]
    row = db.get_current(uid)
    assert row["status"] == "cancelled"


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


def test_subscribe_skips_if_legacy_trial_status(logged_in_client, monkeypatch):
    """Fix 1 : une ligne `subscriptions` historique en statut 'trial' reste
    protégée comme 'active' (#132).

    L'essai applicatif ne crée plus de ligne `subscriptions` du tout (il vit
    entièrement dans `subscriber_state.trial_ends_at`) : ce statut ne peut
    donc plus provenir de la souscription elle-même. Il reste néanmoins une
    valeur valide de `SUBSCRIPTION_STATUSES`, encore produite par
    `webhooks.map_subscription` (cf. `test_webhooks.py::test_map_trial`) et
    encore traitée comme un accès valide par `_ACCESS_STATUSES` /
    `has_active_subscription`. `subscribe()` ne doit donc pas écraser une
    telle ligne, qu'elle soit héritée d'avant la migration ou produite par ce
    chemin webhook générique."""
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
        lambda h, accept_url, cancel_url: (
            f"https://pay.test/{h}?a={accept_url}&c={cancel_url}"
        ),
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
