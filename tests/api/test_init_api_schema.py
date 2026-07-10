import sqlite3


def test_init_api_creates_api_tokens_table(monkeypatch, tmp_path):
    from flask import Flask

    from src.api import init_api, tracking

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    server = Flask(__name__)
    init_api(server)
    try:
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='api_tokens'"
            ).fetchall()
    finally:
        tracking.stop_worker()
    assert rows == [("api_tokens",)]
