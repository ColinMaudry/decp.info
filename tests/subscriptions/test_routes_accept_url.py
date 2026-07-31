"""L'URL de retour du checkout porte le discriminant qui déclenche l'événement
`subscription_trial` côté navigateur (src/assets/goals.js)."""

import pytest

from src.subscriptions import client, db


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


def test_discriminant_present_pour_un_premier_essai(
    logged_in_client, capture_accept, monkeypatch
):
    test_client, _ = logged_in_client
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    monkeypatch.setattr(db, "has_used_trial", lambda user_id: False)

    test_client.post("/subscriptions/subscribe", data={"plan": "simple"})

    assert "souscription=trial" in capture_accept["accept_url"]
    assert "plan=simple" in capture_accept["accept_url"]


def test_pas_de_discriminant_si_essai_deja_consomme(
    logged_in_client, capture_accept, monkeypatch
):
    """no_trial : souscription directe en payant, comptée côté serveur."""
    test_client, _ = logged_in_client
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    monkeypatch.setattr(db, "has_used_trial", lambda user_id: True)

    test_client.post("/subscriptions/subscribe", data={"plan": "simple"})

    assert "accept_url" in capture_accept
    assert "paiement=succes" in capture_accept["accept_url"]
    assert "souscription=" not in capture_accept["accept_url"]


def test_pas_de_discriminant_sous_tous_abonnes(
    logged_in_client, capture_accept, monkeypatch
):
    test_client, _ = logged_in_client
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    monkeypatch.setattr(db, "has_used_trial", lambda user_id: False)

    test_client.post("/subscriptions/subscribe", data={"plan": "simple"})

    assert "accept_url" in capture_accept
    assert "paiement=succes" in capture_accept["accept_url"]
    assert "souscription=" not in capture_accept["accept_url"]
