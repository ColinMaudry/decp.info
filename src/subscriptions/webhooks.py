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


def _payment_proven(sub: dict) -> bool:
    """Vrai si cet abonnement a effectivement donné lieu à un paiement.

    `state` ne peut pas répondre à cette question : la spec Frisbii ne connaît
    que `active`, `expired`, `on_hold` et `pending`, et aucun de ces états ne
    signifie « impayé ». Un abonnement créé sans moyen de paiement reste
    `active` jusqu'à ce que le recouvrement le fasse expirer
    (`expire_reason: "dunning"`), et `grace_duration` retarde encore ce moment.

    Deux preuves suffisantes, l'une ou l'autre :
    - `payment_method_added` : le client a enregistré un moyen de paiement à un
      moment donné (le champ ne repasse jamais à faux) ;
    - `settled_invoices` : au moins une facture a été encaissée.

    La seconde couvre le cas d'un moyen de paiement retiré après coup ; la
    première évite de couper l'accès pendant le laps de temps où la première
    facture n'est pas encore encaissée.
    """
    return (
        bool(sub.get("payment_method_added")) or (sub.get("settled_invoices") or 0) > 0
    )


def map_subscription(sub: dict) -> tuple[str, str | None]:
    """Mappe un objet subscription Frisbii vers (status, current_period_end).

    Les statuts qui ouvrent l'accès payant (`active`, et `cancelled` dont la
    période court encore) exigent une preuve de paiement : sans elle, on
    retombe sur `pending`, qui n'ouvre rien. `trial` échappe volontairement à
    cette règle — un essai est par nature un accès sans paiement.
    """
    status, end = _map_state(sub)
    if status in ("active", "cancelled") and not _payment_proven(sub):
        return "pending", None
    return status, end


def _map_state(sub: dict) -> tuple[str, str | None]:
    """Traduction brute de l'état Frisbii, sans considération de paiement.

    Noms de champs Reepay : state, trial_end, expires, is_cancelled,
    next_period_start.
    """
    state = sub.get("state")
    if state == "expired":
        return "expired", sub.get("expires")
    if sub.get("is_cancelled") or state == "cancelled":
        return "cancelled", sub.get("expires")
    if _in_future(sub.get("trial_end")):
        # Ce mapping alimente db._ACCESS_STATUSES : l'admin peut écrire
        # "trial" à la main sur une ligne subscriptions (status y est
        # éditable, cf. src/admin/tables.py), et une base déployée avant ce
        # chantier peut porter des lignes historiques à ce statut — dans les
        # deux cas, l'accès ne doit pas être coupé. Accessoirement, ce
        # branchement couvre aussi le cas défensif où un plan Frisbii
        # resterait configuré avec un essai malgré le no_trial=True envoyé à
        # la création (src/subscriptions/routes.py::subscribe), qui devrait
        # sinon rendre ce trial_end futur impossible.
        return "trial", sub.get("trial_end")
    if state == "active":
        return "active", sub.get("next_period_start")
    if state == "pending":
        return "pending", None
    return (state or "pending"), sub.get("next_period_start")
