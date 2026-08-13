"""L'essai n'existe plus côté Frisbii (#132) : l'URL de retour du checkout ne
porte donc plus aucun discriminant d'essai (`souscription=trial`), toute
souscription étant immédiatement payante."""

import pytest

from src.subscriptions import client


@pytest.fixture
def capture_accept(monkeypatch):
    """Intercepte l'URL d'acceptation transmise à Frisbii."""
    captured = {}

    def fake_session(plan_handle, handle, accept_url, cancel_url, **kwargs):
        captured["accept_url"] = accept_url
        captured["no_trial"] = kwargs.get("no_trial")
        return "https://checkout.example/session"

    monkeypatch.setattr(client, "create_subscription_session", fake_session)
    monkeypatch.setattr(client, "update_customer", lambda handle, data: {})
    return captured


def test_accept_url_has_no_trial_discriminant(logged_in_client, capture_accept):
    test_client, _ = logged_in_client

    test_client.post("/subscriptions/subscribe", data={"plan": "simple"})

    assert "accept_url" in capture_accept
    assert "paiement=succes" in capture_accept["accept_url"]
    assert "souscription=trial" not in capture_accept["accept_url"]
    assert capture_accept["no_trial"] is True
