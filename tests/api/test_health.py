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
    assert resp.get_json() == {"status": "ok"}


def test_health_via_real_app():
    """Vérifie que init_api est bien branché dans src.app."""
    from src.app import app as dash_app

    resp = dash_app.server.test_client().get("/api/v1/health")
    assert resp.status_code == 200
