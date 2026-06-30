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
        "label": "Abonnement",
        "prix_ht": 20,
        "description": "Accès aux fonctionnalités supplémentaires de colibre.",
    },
    "soutien": {
        "env": "FRISBII_PLAN_SOUTIEN",
        "label": "Abonnement de soutien ✊",
        "prix_ht": 50,
        "description": "Mêmes fonctionnalités, contribution renforcée au projet.",
    },
}


def resolve_handle(key: str) -> str | None:
    meta = PLANS.get(key)
    if meta is None:
        return None
    h = _handle(meta["env"])
    return h if h else None


def plan_meta(key: str) -> dict | None:
    meta = PLANS.get(key)
    if meta is None:
        return None
    h = _handle(meta["env"])
    return {
        "key": key,
        "handle": h if h else None,
        "label": meta["label"],
        "prix_ht": meta["prix_ht"],
        "description": meta["description"],
    }


def _parse_trial_interval(plan: dict) -> int | None:
    unit = plan.get("trial_interval_unit", "")
    length = plan.get("trial_interval_length")
    if unit == "days" and isinstance(length, int) and length > 0:
        return length
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
    # L'API Frisbii/Reepay renvoie une liste de versions ; on prend la dernière (la plus récente).
    if isinstance(plan, list):
        plan = plan[-1] if plan else {}
    days = _parse_trial_interval(plan)
    _trial_cache[handle] = (now, days)
    return days
