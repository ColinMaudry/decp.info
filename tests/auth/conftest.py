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
def mail_outbox(app):
    mail = app.extensions["mail"]
    with mail.record_messages() as outbox:
        yield outbox
