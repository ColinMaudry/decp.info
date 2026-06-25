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
        {"state": "active", "next_period_start": nxt}
    )
    assert status == "active"
    assert end == nxt


def test_map_cancelled():
    exp = _future()
    status, end = webhooks.map_subscription(
        {"state": "active", "is_cancelled": True, "expires": exp}
    )
    assert status == "cancelled"
    assert end == exp


def test_map_expired():
    status, end = webhooks.map_subscription(
        {"state": "expired", "expires": "2020-01-01T00:00:00Z"}
    )
    assert status == "expired"
