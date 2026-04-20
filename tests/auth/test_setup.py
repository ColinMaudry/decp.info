import pytest
from flask import Flask
from flask_login import current_user

from src.auth.setup import init_auth, safe_next


def test_safe_next_allows_relative_path():
    assert safe_next("/acheteur?id=1") == "/acheteur?id=1"


def test_safe_next_rejects_absolute_urls():
    assert safe_next("https://evil.com/phish") == "/"


def test_safe_next_rejects_protocol_relative():
    assert safe_next("//evil.com") == "/"


def test_safe_next_rejects_empty():
    assert safe_next("") == "/"
    assert safe_next(None) == "/"


def test_safe_next_custom_fallback():
    assert safe_next("", fallback="/compte") == "/compte"


def test_init_auth_requires_secret_key(monkeypatch, users_db_path):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    app = Flask(__name__)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        init_auth(app)


def test_init_auth_anonymous_user_not_authenticated(users_db_path):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    init_auth(app)
    with app.test_request_context("/"):
        assert current_user.is_authenticated is False
