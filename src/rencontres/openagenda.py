import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from src.utils.cache import cache

logger = logging.getLogger(__name__)

_API_BASE = "https://api.openagenda.com/v2"


@dataclass
class Evenement:
    uid: str
    titre: str
    debut: datetime  # timezone-aware, offset OpenAgenda (non converti en UTC)
    fin: datetime
    lieu_nom: str | None
    lieu_ville: str | None
    description: str | None
    visio_url: str | None


def _fr(champ: dict | None) -> str | None:
    """Extrait le français d'un champ multilingue OpenAgenda ({'fr': …})."""
    if not champ:
        return None
    return champ.get("fr") or next(iter(champ.values()), None)


def _creneau(ev: dict) -> dict | None:
    """Prochain créneau : nextTiming (déjà calculé) sinon premier timing."""
    timing = ev.get("nextTiming")
    if timing:
        return timing
    timings = ev.get("timings") or []
    return timings[0] if timings else None


def _normaliser(ev: dict) -> Evenement | None:
    creneau = _creneau(ev)
    if not creneau:
        return None
    location = ev.get("location") or {}
    return Evenement(
        uid=str(ev["uid"]),
        titre=_fr(ev.get("title")) or "",
        debut=datetime.fromisoformat(creneau["begin"]),
        fin=datetime.fromisoformat(creneau["end"]),
        lieu_nom=location.get("name"),
        lieu_ville=location.get("city"),
        description=_fr(ev.get("description")),
        visio_url=ev.get("onlineAccessLink"),
    )


@cache.memoize(timeout=3600)
def fetch_rencontres() -> list[Evenement]:
    """Événements à venir de l'agenda colibre, normalisés. Cache 1 h.

    Appel à l'API OpenAgenda. Toute erreur (config manquante, réseau, quota,
    parsing) est loggée et renvoie [] : la page ne plante jamais.
    """
    key = os.getenv("OPENAGENDA_API_KEY", "")
    agenda = os.getenv("OPENAGENDA_AGENDA_UID", "")
    if not key or not agenda:
        logger.warning("OPENAGENDA_API_KEY / OPENAGENDA_AGENDA_UID non configurés")
        return []
    try:
        resp = httpx.get(
            f"{_API_BASE}/agendas/{agenda}/events",
            params={
                "key": key,
                "timings[gte]": datetime.now(timezone.utc).isoformat(),
                "sort": "timings.asc",
                "detailed": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        events = resp.json().get("events", [])
    except Exception as exc:
        logger.warning("Récupération OpenAgenda échouée : %s", exc)
        return []
    resultats: list[Evenement] = []
    for ev in events:
        try:
            norm = _normaliser(ev)
        except Exception as exc:
            logger.warning("Événement OpenAgenda ignoré : %s", exc)
            continue
        if norm is not None:
            resultats.append(norm)
    return resultats
