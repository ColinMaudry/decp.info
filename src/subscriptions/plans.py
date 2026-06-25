import os
import time

from src.subscriptions import client
from src.utils import logger

_TTL_SECONDS = 3600
_trial_cache: dict[str, tuple[float, int | None]] = {}


def _handle(env_name: str) -> str:
    return os.getenv(env_name, "")


PLANS = {
    "simple": {
        "env": "FRISBII_PLAN_SIMPLE",
        "label": "Abonnement simple",
        "prix_ht": 20,
        "description": "Accès aux fonctionnalités premium de decp.info.",
    },
    "soutien": {
        "env": "FRISBII_PLAN_SOUTIEN",
        "label": "Abonnement de soutien",
        "prix_ht": 50,
        "description": "Mêmes fonctionnalités, contribution renforcée au projet.",
    },
}


def resolve_handle(key: str) -> str | None:
    meta = PLANS.get(key)
    return _handle(meta["env"]) if meta else None


def plan_meta(key: str) -> dict | None:
    meta = PLANS.get(key)
    if meta is None:
        return None
    return {
        "key": key,
        "handle": _handle(meta["env"]),
        "label": meta["label"],
        "prix_ht": meta["prix_ht"],
        "description": meta["description"],
    }


def _parse_trial_interval(value) -> int | None:
    # Reepay/Frisbii renvoie une durée type "2d" (jours), "1m" (mois), etc.
    # On ne sait afficher que les jours pour l'instant ; format à confirmer.
    if not value or not isinstance(value, str):
        return None
    value = value.strip().lower()
    if value.endswith("d") and value[:-1].isdigit():
        return int(value[:-1])
    return None


def trial_days(key: str) -> int | None:
    handle = resolve_handle(key)
    if not handle:
        return None
    now = time.monotonic()
    cached = _trial_cache.get(handle)
    if cached and now - cached[0] < _TTL_SECONDS:
        return cached[1]
    try:
        plan = client.get_plan(handle)
    except client.FrisbiiError:
        logger.warning("Impossible de lire le plan Frisbii %s", handle)
        return cached[1] if cached else None
    days = _parse_trial_interval(plan.get("trial_interval"))
    _trial_cache[handle] = (now, days)
    return days
