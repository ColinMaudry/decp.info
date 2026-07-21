from datetime import datetime, timedelta, timezone

from src.app import app
from src.rencontres import openagenda
from src.rencontres.openagenda import Evenement

_PARIS = timezone(timedelta(hours=2))


def _ev(uid="42"):
    return Evenement(
        uid=uid,
        titre="Rencontre colibre",
        debut=datetime(2026, 7, 27, 10, 0, tzinfo=_PARIS),
        fin=datetime(2026, 7, 27, 11, 0, tzinfo=_PARIS),
        lieu_nom=None,
        lieu_ville=None,
        description="Discussion",
        visio_url="https://visio.example/xyz",
    )


def test_route_ics_uid_connu(monkeypatch):
    monkeypatch.setattr(openagenda, "fetch_rencontres", lambda: [_ev("42")])
    resp = app.server.test_client().get("/rencontres/42.ics")
    assert resp.status_code == 200
    assert resp.mimetype == "text/calendar"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert b"BEGIN:VCALENDAR" in resp.data


def test_route_ics_uid_inconnu(monkeypatch):
    monkeypatch.setattr(openagenda, "fetch_rencontres", lambda: [_ev("42")])
    resp = app.server.test_client().get("/rencontres/999.ics")
    assert resp.status_code == 404
