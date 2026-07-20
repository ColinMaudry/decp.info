from datetime import datetime

from flask import Flask

from src.api import init_api


def _make_app():
    app = Flask(__name__)
    init_api(app)
    return app


def test_health_returns_ok_without_auth():
    app = _make_app()
    resp = app.test_client().get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_health_via_real_app():
    """Vérifie que init_api est bien branché dans src.app."""
    from src.app import app as dash_app

    resp = dash_app.server.test_client().get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_health_expose_la_fraicheur_des_donnees():
    """Un rebuild raté fait servir des données périmées silencieusement.

    `_ensure_database` rattrape l'échec en réutilisant le DuckDB existant :
    l'app démarre normalement et rien ne signale que les données datent.
    """
    resp = _make_app().test_client().get("/api/v1/health")

    donnees = resp.get_json()["donnees"]
    datetime.fromisoformat(donnees["construites_le"])
    assert donnees["age_heures"] >= 0


def test_health_renvoie_503_si_duckdb_injoignable(monkeypatch):
    """La sonde doit interroger DuckDB, pas se contenter d'un 200 statique."""

    def _echec():
        raise RuntimeError("DuckDB injoignable")

    monkeypatch.setattr("src.api.routes.get_cursor", _echec)

    resp = _make_app().test_client().get("/api/v1/health")

    assert resp.status_code == 503
    assert resp.get_json()["status"] == "error"
