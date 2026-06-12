import pytest


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Une SQLite éphémère pour les tests qui modifient la DB."""
    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    from src.api import tokens_db

    tokens_db.init_schema(db_path)
    return db_path


@pytest.fixture
def api_client(monkeypatch, tmp_path):
    """Client Flask test avec USERS_DB_PATH éphémère et blueprint API monté."""
    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    from flask import Flask

    from src.api import init_api, tokens_db, tracking

    tokens_db.init_schema(db_path)
    server = Flask(__name__)
    init_api(server)
    yield server.test_client(), db_path
    tracking.stop_worker()


@pytest.fixture
def valid_token_header(api_client):
    from src.api import tokens_db

    _, db_path = api_client
    token, _ = tokens_db.create_token(db_path, "test-token")
    return {"Authorization": f"Bearer {token}"}
