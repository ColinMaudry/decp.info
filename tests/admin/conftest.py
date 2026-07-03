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
def admin_app(users_db_path, monkeypatch):
    from flask import Flask

    from src.auth.setup import init_auth
    from src.subscriptions.setup import init_subscriptions

    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    monkeypatch.setenv("FRISBII_WEBHOOK_SECRET", "s3cr3t")
    flask_app = Flask(__name__)
    flask_app.config["WTF_CSRF_ENABLED"] = False
    init_auth(flask_app)
    init_subscriptions(flask_app)
    return flask_app


@pytest.fixture
def admin_client(admin_app):
    return admin_app.test_client()


@pytest.fixture
def logged_in_admin_client(admin_app, monkeypatch):
    from src.auth import db as auth_db

    monkeypatch.setenv("ADMIN_EMAIL", "admin@ex.fr")
    uid = auth_db.create_user("admin@ex.fr", "hash")
    auth_db.set_email_verified(uid)
    client = admin_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)
        sess["_fresh"] = True
    return client, uid
