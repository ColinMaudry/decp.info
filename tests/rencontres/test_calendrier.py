from datetime import datetime, timedelta, timezone

from src.rencontres.calendrier import ics_evenement, lien_google, lien_outlook
from src.rencontres.openagenda import Evenement

_PARIS = timezone(timedelta(hours=2))


def _ev(
    titre="Rencontre colibre",
    description="Discussion",
    visio="https://visio.example/xyz",
):
    return Evenement(
        uid="42",
        titre=titre,
        debut=datetime(2026, 7, 27, 10, 0, tzinfo=_PARIS),  # 08:00 UTC
        fin=datetime(2026, 7, 27, 11, 0, tzinfo=_PARIS),  # 09:00 UTC
        lieu_nom=None,
        lieu_ville=None,
        description=description,
        visio_url=visio,
    )


def test_lien_google_convertit_en_utc():
    url = lien_google(_ev())
    assert url.startswith("https://calendar.google.com/calendar/render?")
    assert "action=TEMPLATE" in url
    # 10:00+02:00 -> 08:00Z ; les jetons compacts apparaissent littéralement
    assert "20260727T080000Z" in url
    assert "20260727T090000Z" in url
    # le lien visio est aussi dans le corps (details) : "Visioconf" et l'hôte
    # sont des sous-chaînes ASCII sans caractère réservé, donc inchangées par
    # quote() — mais quote() encode bien ':' en %3A ailleurs dans la valeur
    # (ex. "https:" -> "https%3A", voir test_lien_outlook_utilise_iso_utc).
    assert "Visioconf" in url
    assert "visio.example" in url


def test_lien_outlook_utilise_iso_utc():
    url = lien_outlook(_ev())
    assert url.startswith("https://outlook.live.com/calendar/0/deeplink/compose")
    assert "rru=addevent" in url
    # ISO UTC, encodé (les ':' deviennent %3A)
    assert "2026-07-27T08%3A00%3A00Z" in url
    # le lien visio est aussi dans le corps (body)
    assert "Visioconf" in url
    assert "visio.example" in url


def test_ics_structure_et_dates_utc():
    ics = ics_evenement(_ev())
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert ics.endswith("END:VCALENDAR\r\n")
    assert "\r\n" in ics
    assert "UID:42@colibre.fr" in ics
    assert "DTSTART:20260727T080000Z" in ics
    assert "DTEND:20260727T090000Z" in ics
    assert "SUMMARY:Rencontre colibre" in ics
    assert "URL:https://visio.example/xyz" in ics
    # le lien visio est aussi dans la DESCRIPTION
    assert "Visioconférence : https://visio.example/xyz" in ics


def test_visio_dans_le_corps_meme_avec_lieu_physique():
    # Cas hybride : lieu physique ET visio. La visio ne doit PAS être perdue.
    ev = _ev()
    ev.lieu_nom = "Mairie"
    ev.lieu_ville = "Nantes"
    google = lien_google(ev)
    assert "Nantes" in google  # location = lieu physique
    assert "visio.example" in google  # visio conservée dans le corps
    outlook = lien_outlook(ev)
    assert "visio.example" in outlook
    ics = ics_evenement(ev)
    assert "LOCATION:Mairie — Nantes" in ics
    assert "URL:https://visio.example/xyz" in ics
    assert "Visioconférence : https://visio.example/xyz" in ics  # dans DESCRIPTION


def test_ics_echappe_les_caracteres_speciaux():
    ics = ics_evenement(_ev(titre="Atelier, DECP; libre", description="a\nb"))
    assert "SUMMARY:Atelier\\, DECP\\; libre" in ics
    # description "a\nb" échappée en tête de DESCRIPTION (avant la ligne visio)
    assert "DESCRIPTION:a\\nb" in ics


def test_ics_echappe_le_backslash_dans_le_titre():
    ics = ics_evenement(_ev(titre="Atelier \\ pratique"))
    lignes = ics.split("\r\n")
    ligne_summary = next(ligne for ligne in lignes if ligne.startswith("SUMMARY:"))
    assert ligne_summary == "SUMMARY:Atelier \\\\ pratique"


def test_ics_description_sans_cr_bare():
    ics = ics_evenement(_ev(description="a\r\nb"))
    lignes = ics.split("\r\n")
    ligne_description = next(
        ligne for ligne in lignes if ligne.startswith("DESCRIPTION:")
    )
    assert "\r" not in ligne_description
    assert "a\\nb" in ligne_description
