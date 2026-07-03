import pytest


@pytest.fixture
def users_db_path(monkeypatch, tmp_path):
    from src import migrations
    from src.auth import db as auth_db
    from src.auth.db import reset_conn_for_tests
    from src.subscriptions import db as sub_db

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    reset_conn_for_tests()
    auth_db.init_schema()
    sub_db.init_schema()
    migrations.apply_pending()
    yield db_path
    reset_conn_for_tests()
