import pytest


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Une SQLite éphémère pour les tests qui modifient la DB."""
    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    from src.api import tokens_db

    tokens_db.init_schema(db_path)
    return db_path
