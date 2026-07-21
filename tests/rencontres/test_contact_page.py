from datetime import datetime, timedelta, timezone

from src.pages.a_propos import contact
from src.rencontres import openagenda
from src.rencontres.openagenda import Evenement

_PARIS = timezone(timedelta(hours=2))


def _ev():
    return Evenement(
        uid="42",
        titre="Rencontre colibre juillet",
        debut=datetime(2026, 7, 27, 10, 0, tzinfo=_PARIS),
        fin=datetime(2026, 7, 27, 11, 0, tzinfo=_PARIS),
        lieu_nom=None,
        lieu_ville=None,
        description="Discussion libre",
        visio_url="https://visio.example/xyz",
    )


def test_section_affiche_les_evenements(monkeypatch):
    monkeypatch.setattr(openagenda, "fetch_rencontres", lambda: [_ev()])
    rendu = str(contact.layout())
    assert "Prochaines rencontres" in rendu
    assert "Rencontre colibre juillet" in rendu
    assert "27 juillet 2026 à 10h00" in rendu
    assert "/rencontres/42.ics" in rendu
    assert "Rejoindre en visio" in rendu


def test_section_message_si_aucun_evenement(monkeypatch):
    monkeypatch.setattr(openagenda, "fetch_rencontres", lambda: [])
    rendu = str(contact.layout())
    assert "bientôt annoncées" in rendu
