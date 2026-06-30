import pytest

# Dash minimal pour que register_page() fonctionne dans les tests de pages de ce
# répertoire (CONFIG peuplé). Instancié une seule fois, ici, avant tout import de page.
from dash import Dash as _Dash

_Dash(__name__, use_pages=True, pages_folder="", assets_folder="assets")


@pytest.fixture
def users_db_path(monkeypatch, tmp_path):
    from src.auth.db import reset_conn_for_tests

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    reset_conn_for_tests()
    yield db_path
    reset_conn_for_tests()
