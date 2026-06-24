import pytest


@pytest.fixture
def users_db_path(monkeypatch, tmp_path):
    from src.auth.db import reset_conn_for_tests

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    reset_conn_for_tests()
    yield db_path
    reset_conn_for_tests()


@pytest.fixture
def app(users_db_path, monkeypatch):
    from flask import Flask

    from src.auth.setup import init_auth

    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    app = Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = False
    init_auth(app)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mail_outbox(app, monkeypatch):
    from src.auth import mailer

    calls = []

    class _Msg:
        def __init__(self, call):
            self._call = call

        @property
        def recipients(self):
            return [to.email for to in self._call["to"]]

    class _FakeTransac:
        def send_transac_email(self, **kwargs):
            calls.append(_Msg(kwargs))

    class _FakeClient:
        def __init__(self):
            self.transactional_emails = _FakeTransac()

    monkeypatch.setattr(mailer, "_client", _FakeClient())
    monkeypatch.setenv("BREVO_TEMPLATE_VERIFY_ID", "11")
    monkeypatch.setenv("BREVO_TEMPLATE_RESET_ID", "22")
    yield calls
