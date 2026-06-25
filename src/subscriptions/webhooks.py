import hashlib
import hmac
from datetime import datetime, timezone


def verify_signature(payload: dict, secret: str) -> bool:
    # Schéma Reepay/Frisbii : HMAC-SHA256(secret, timestamp + id), hex.
    # À confirmer dans la doc webhooks Frisbii lors de l'intégration.
    if not secret:
        return False
    timestamp = payload.get("timestamp", "")
    event_id = payload.get("id", "")
    received = payload.get("signature", "")
    expected = hmac.new(
        secret.encode(), (timestamp + event_id).encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received)


def _in_future(value) -> bool:
    if not value:
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) > datetime.now(
            timezone.utc
        )
    except ValueError:
        return False


def map_subscription(sub: dict) -> tuple[str, str | None]:
    """Mappe un objet subscription Frisbii vers (status, current_period_end).

    Noms de champs Reepay (à confirmer) : state, trial_end, expires,
    is_cancelled, next_period_start.
    """
    state = sub.get("state")
    if state == "expired":
        return "expired", sub.get("expires")
    if sub.get("is_cancelled") or state == "cancelled":
        return "cancelled", sub.get("expires")
    if _in_future(sub.get("trial_end")):
        return "trial", sub.get("trial_end")
    if state == "active":
        return "active", sub.get("next_period_start")
    if state == "pending":
        return "pending", None
    return (state or "pending"), sub.get("next_period_start")
