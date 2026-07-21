import json
from pathlib import Path

import httpx

from src.rencontres import openagenda
from src.rencontres.openagenda import Evenement

_EVENT = json.loads((Path(__file__).parent / "event.json").read_text())["event"]


def test_normaliser_evenement_en_ligne():
    ev = openagenda._normaliser(_EVENT)
    assert isinstance(ev, Evenement)
    assert ev.uid == "41344161"
    assert ev.titre == "Nouveautés decp.info/colibre et discussion libre"
    assert ev.description.startswith("Rencontre avec les utilisateurs")
    # nextTiming : 2026-07-27T10:00:00+02:00
    assert ev.debut.year == 2026 and ev.debut.hour == 10
    assert ev.debut.utcoffset().total_seconds() == 2 * 3600
    assert ev.fin.hour == 11
    # événement en ligne : pas de lieu
    assert ev.lieu_nom is None
    assert ev.lieu_ville is None
    assert ev.visio_url == "https://kmeet.infomaniak.com/0kywff4pcpetv425cfutesvz"


def test_fetch_rencontres_normalise_la_liste(monkeypatch):
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"events": [_EVENT]}

    monkeypatch.setenv("OPENAGENDA_API_KEY", "k")
    monkeypatch.setenv("OPENAGENDA_AGENDA_UID", "3512069")
    monkeypatch.setattr(openagenda.httpx, "get", lambda *a, **k: _FakeResp())
    result = openagenda.fetch_rencontres.uncached()
    assert len(result) == 1
    assert result[0].uid == "41344161"


def test_fetch_rencontres_renvoie_liste_vide_si_api_echoue(monkeypatch):
    def _boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setenv("OPENAGENDA_API_KEY", "k")
    monkeypatch.setenv("OPENAGENDA_AGENDA_UID", "3512069")
    monkeypatch.setattr(openagenda.httpx, "get", _boom)
    assert openagenda.fetch_rencontres.uncached() == []


def test_fetch_rencontres_renvoie_liste_vide_si_non_configure(monkeypatch):
    monkeypatch.delenv("OPENAGENDA_API_KEY", raising=False)
    monkeypatch.delenv("OPENAGENDA_AGENDA_UID", raising=False)
    assert openagenda.fetch_rencontres.uncached() == []


def test_fetch_rencontres_ignore_evenement_malforme(monkeypatch):
    evenement_malforme = {**_EVENT, "title": "pas un dict"}

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"events": [evenement_malforme, _EVENT]}

    monkeypatch.setenv("OPENAGENDA_API_KEY", "k")
    monkeypatch.setenv("OPENAGENDA_AGENDA_UID", "3512069")
    monkeypatch.setattr(openagenda.httpx, "get", lambda *a, **k: _FakeResp())
    result = openagenda.fetch_rencontres.uncached()
    assert len(result) == 1
    assert result[0].uid == "41344161"


def test_normaliser_nettoie_visio_url_des_caracteres_de_controle():
    ev_dict = {
        "uid": 1,
        "title": {"fr": "Titre"},
        "nextTiming": {
            "begin": "2026-07-27T10:00:00+02:00",
            "end": "2026-07-27T11:00:00+02:00",
        },
        "onlineAccessLink": "https://visio.example/x\r\nBEGIN:VALARM",
    }
    ev = openagenda._normaliser(ev_dict)
    assert ev.visio_url is not None
    assert "\r" not in ev.visio_url and "\n" not in ev.visio_url


def test_fetch_rencontres_renvoie_liste_vide_si_payload_non_dict(monkeypatch):
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return []

    monkeypatch.setenv("OPENAGENDA_API_KEY", "k")
    monkeypatch.setenv("OPENAGENDA_AGENDA_UID", "3512069")
    monkeypatch.setattr(openagenda.httpx, "get", lambda *a, **k: _FakeResp())
    assert openagenda.fetch_rencontres.uncached() == []
