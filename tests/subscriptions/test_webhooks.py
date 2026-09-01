import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from src.subscriptions import webhooks


def _sign(secret, timestamp, event_id):
    return hmac.new(
        secret.encode(), (timestamp + event_id).encode(), hashlib.sha256
    ).hexdigest()


def test_verify_signature_accepts_valid():
    payload = {"id": "evt_1", "timestamp": "2026-06-25T10:00:00Z"}
    payload["signature"] = _sign("s3cr3t", payload["timestamp"], payload["id"])
    assert webhooks.verify_signature(payload, "s3cr3t") is True


def test_verify_signature_rejects_tampered():
    payload = {
        "id": "evt_1",
        "timestamp": "2026-06-25T10:00:00Z",
        "signature": "deadbeef",
    }
    assert webhooks.verify_signature(payload, "s3cr3t") is False


def test_verify_signature_rejects_without_secret():
    payload = {"id": "evt_1", "timestamp": "t", "signature": "x"}
    assert webhooks.verify_signature(payload, "") is False


def _future():
    return (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()


def test_map_trial():
    status, end = webhooks.map_subscription(
        {"state": "active", "trial_end": _future(), "next_period_start": _future()}
    )
    assert status == "trial"


def test_map_active():
    nxt = _future()
    status, end = webhooks.map_subscription(
        {"state": "active", "payment_method_added": True, "next_period_start": nxt}
    )
    assert status == "active"
    assert end == nxt


def test_map_cancelled():
    exp = _future()
    status, end = webhooks.map_subscription(
        {
            "state": "active",
            "is_cancelled": True,
            "payment_method_added": True,
            "expires": exp,
        }
    )
    assert status == "cancelled"
    assert end == exp


def test_map_expired():
    status, end = webhooks.map_subscription(
        {"state": "expired", "expires": "2020-01-01T00:00:00Z"}
    )
    assert status == "expired"


def test_map_active_sans_moyen_de_paiement_n_ouvre_pas_l_acces():
    """Un abonnement `active` sans paiement ne doit jamais donner accès.

    `state` ne peut pas servir de preuve de paiement : la spec Frisbii ne
    connaît que `active`, `expired`, `on_hold` et `pending`, et un abonnement
    créé sans moyen de paiement reste `active` jusqu'à ce que le recouvrement
    le fasse expirer.
    """
    status, end = webhooks.map_subscription(
        {
            "state": "active",
            "payment_method_added": False,
            "settled_invoices": 0,
            "next_period_start": _future(),
        }
    )
    assert status == "pending"
    assert end is None


def test_map_active_sans_champ_de_paiement_n_ouvre_pas_l_acces():
    """Payload incomplet : on refuse l'accès plutôt que de le supposer acquis."""
    status, _ = webhooks.map_subscription({"state": "active"})
    assert status == "pending"


def test_map_active_avec_facture_encaissee():
    """Moyen de paiement retiré depuis, mais une facture a été encaissée."""
    status, _ = webhooks.map_subscription(
        {
            "state": "active",
            "payment_method_added": False,
            "settled_invoices": 2,
            "next_period_start": _future(),
        }
    )
    assert status == "active"


def test_map_cancelled_sans_paiement_n_ouvre_pas_l_acces():
    """Un abonnement fantôme résilié ne doit pas rouvrir l'accès via `expires`.

    `has_active_subscription` accorde l'accès à un `cancelled` dont la période
    court encore : sans cette garde, résilier un abonnement jamais payé
    suffirait à s'offrir une période d'accès gratuite.
    """
    status, _ = webhooks.map_subscription(
        {
            "state": "active",
            "is_cancelled": True,
            "expires": _future(),
            "payment_method_added": False,
            "settled_invoices": 0,
        }
    )
    assert status == "pending"


def test_map_trial_reste_accessible_sans_paiement():
    """L'essai Frisbii est par nature un accès sans paiement : pas de garde ici.

    Cas défensif seulement — colibre envoie toujours `no_trial=True` — mais si
    un plan restait configuré avec un essai, couper l'accès serait un
    contresens.
    """
    status, _ = webhooks.map_subscription(
        {
            "state": "active",
            "trial_end": _future(),
            "payment_method_added": False,
            "settled_invoices": 0,
        }
    )
    assert status == "trial"
