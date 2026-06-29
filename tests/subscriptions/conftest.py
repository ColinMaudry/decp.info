import json as _json

import pytest

# Initialise un Dash minimal pour que register_page() fonctionne dans les tests
# unitaires de pages (pas besoin du serveur complet — juste que CONFIG soit peuplé).
from dash import Dash as _Dash

_Dash(__name__, use_pages=True, pages_folder="", assets_folder="assets")

from src.pages import compte_abonnement  # noqa: F401, E402  # doit venir après Dash()


class FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    @property
    def text(self):
        return _json.dumps(self._payload)


@pytest.fixture
def users_db_path(monkeypatch, tmp_path):
    from src.auth.db import reset_conn_for_tests

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    reset_conn_for_tests()
    yield db_path
    reset_conn_for_tests()


@pytest.fixture
def fake_httpx(monkeypatch):
    """Capture les appels httpx.request du client Frisbii et renvoie des réponses programmées."""
    from src.subscriptions import client

    calls = []
    queue = []

    def _fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        if queue:
            return queue.pop(0)
        return FakeResponse(200, {})

    monkeypatch.setenv("FRISBII_API_KEY", "priv_test")
    monkeypatch.setenv("FRISBII_API_BASE_URL", "https://api.test")
    monkeypatch.setattr(client.httpx, "request", _fake_request)
    return {"calls": calls, "queue": queue, "Response": FakeResponse}


@pytest.fixture
def sub_app(users_db_path, monkeypatch):
    from flask import Flask

    from src.auth.setup import init_auth
    from src.subscriptions.setup import init_subscriptions

    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    monkeypatch.setenv("FRISBII_WEBHOOK_SECRET", "s3cr3t")
    app = Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = False
    init_auth(app)
    init_subscriptions(app)
    return app


@pytest.fixture
def app_context(sub_app):
    """Fournit un contexte Flask pour les tests unitaires (ex. tests de composants Dash)."""
    with sub_app.test_request_context():
        yield sub_app


@pytest.fixture(autouse=True)
def _ensure_request_context(sub_app):
    """Auto-use fixture pour garantir un contexte request Flask dans tous les tests du répertoire."""
    with sub_app.test_request_context():
        yield


@pytest.fixture
def logged_in_client(sub_app):
    from src.auth import db as auth_db

    auth_db.init_schema()
    uid = auth_db.create_user("sub@ex.fr", "hash")
    auth_db.set_email_verified(uid)
    client = sub_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)
        sess["_fresh"] = True
    return client, uid
