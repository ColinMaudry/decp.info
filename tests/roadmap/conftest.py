import pytest

# Importer l'app complète à la collecte : sa découverte use_pages enregistre
# chaque page (et ses @callback) exactement une fois, en contexte propre. Un Dash
# minimal ad hoc suivi d'imports de pages dans les tests provoque un double
# enregistrement des @callback (Dash ré-exécute chaque page via exec_module
# pendant la découverte de src.app), d'où "Duplicate callback outputs" qui casse
# le rendu de toutes les pages dans la suite Selenium. En important src.app ici,
# la découverte tourne en premier et les imports ultérieurs de pages sont mis en
# cache. Voir aussi tests/subscriptions/conftest.py.
from src.app import app  # noqa: F401, E402


@pytest.fixture
def users_db_path(monkeypatch, tmp_path):
    from src.auth.db import reset_conn_for_tests

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    reset_conn_for_tests()
    yield db_path
    reset_conn_for_tests()
