from datetime import datetime, timezone
from urllib.parse import quote

from src.rencontres.openagenda import Evenement


def _compact_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lieu(ev: Evenement) -> str:
    return " — ".join(p for p in (ev.lieu_nom, ev.lieu_ville) if p)


def _query(params: dict[str, str]) -> str:
    return "&".join(f"{k}={quote(str(v))}" for k, v in params.items())


def _corps(ev: Evenement) -> str:
    """Corps de l'événement : description + lien visio (si présent).

    Le lien visio est ajouté ici — en plus de location/URL — pour qu'il soit
    présent et cliquable dans le corps des trois cibles, y compris pour un
    événement hybride (lieu physique + visio) où location porte l'adresse.
    """
    parties = []
    if ev.description:
        parties.append(ev.description)
    if ev.visio_url:
        parties.append(f"Visioconférence : {ev.visio_url}")
    return "\n\n".join(parties)


def lien_google(ev: Evenement) -> str:
    params = {
        "action": "TEMPLATE",
        "text": ev.titre,
        "dates": f"{_compact_utc(ev.debut)}/{_compact_utc(ev.fin)}",
        "details": _corps(ev),
        "location": _lieu(ev) or ev.visio_url or "",
    }
    return f"https://calendar.google.com/calendar/render?{_query(params)}"


def lien_outlook(ev: Evenement) -> str:
    params = {
        "path": "/calendar/action/compose",
        "rru": "addevent",
        "subject": ev.titre,
        "startdt": _iso_utc(ev.debut),
        "enddt": _iso_utc(ev.fin),
        "body": _corps(ev),
        "location": _lieu(ev) or ev.visio_url or "",
    }
    return f"https://outlook.live.com/calendar/0/deeplink/compose?{_query(params)}"


def _echapper(texte: str) -> str:
    # RFC 5545 : backslash d'abord, puis ; , et sauts de ligne.
    return (
        texte.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def ics_evenement(ev: Evenement) -> str:
    lignes = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//colibre//rencontres//FR",
        "BEGIN:VEVENT",
        f"UID:{ev.uid}@colibre.fr",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{_compact_utc(ev.debut)}",
        f"DTEND:{_compact_utc(ev.fin)}",
        f"SUMMARY:{_echapper(ev.titre)}",
    ]
    corps = _corps(ev)
    if corps:
        lignes.append(f"DESCRIPTION:{_echapper(corps)}")
    lieu = _lieu(ev) or ev.visio_url
    if lieu:
        lignes.append(f"LOCATION:{_echapper(lieu)}")
    if ev.visio_url:
        lignes.append(f"URL:{ev.visio_url}")
    lignes += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lignes) + "\r\n"
