import pytest
from flask import Flask

from src.auth.setup import init_auth


@pytest.fixture
def csrf_app(users_db_path, monkeypatch):
    monkeypatch.setenv("WTF_CSRF_ENABLED", "True")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    app = Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = True
    init_auth(app)
    return app


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def test_post_without_csrf_rejected(csrf_client, users_db_path):
    resp = csrf_client.post(
        "/auth/signup",
        data={
            "email": "a@b.c",
            "password": "password12",
            "password_confirm": "password12",
        },
    )
    assert resp.status_code == 400  # CSRF failed
