import os


def _handle(env_name: str) -> str:
    return os.getenv(env_name, "")


PLANS = {
    "simple": {
        "env": "FRISBII_PLAN_SIMPLE",
        "label": "Abonnement",
        "prix_ht": 20,
        "description": "Accès aux fonctionnalités supplémentaires de colibre.",
        "trial_days": 2,
    },
    "soutien": {
        "env": "FRISBII_PLAN_SOUTIEN",
        "label": "Abonnement de soutien ✊",
        "prix_ht": 50,
        "description": "Mêmes fonctionnalités, contribution renforcée au projet.",
        "trial_days": 2,
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


def trial_days(key: str) -> int | None:
    if not resolve_handle(key):
        return None
    return PLANS[key]["trial_days"]
