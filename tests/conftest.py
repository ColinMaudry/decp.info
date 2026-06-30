import datetime
import os
from pathlib import Path

import polars as pl
import pytest
from selenium.webdriver.chrome.options import Options

_TEST_DATA = [
    {
        "uid": "1",
        "id": "1",
        "acheteur_nom": "ACHETEUR 1",
        "acheteur_id": "123",
        "titulaire_nom": "TITULAIRE 1",
        "titulaire_id": "345",
        "montant": 10,
        "dateNotification": datetime.date(2025, 1, 1),
        "codeCPV": "71600000",
        "donneesActuelles": True,
        "acheteur_departement_code": "75",
        "acheteur_departement_nom": "Paris",
        "acheteur_commune_nom": "Paris",
        "titulaire_departement_code": "35",
        "titulaire_departement_nom": "Ille-et-Vilaine",
        "titulaire_commune_nom": "Rennes",
        "titulaire_distance": 10,
        "titulaire_typeIdentifiant": "SIRET",
        "objet": "Objet test",
        "dureeRestanteMois": 12,
        "lieuExecution_code": "75001",
        "sourceFile": "test.xml",
        "sourceDataset": "test_dataset",
        "datePublicationDonnees": datetime.date(2025, 1, 1),
        "considerationsSociales": "",
        "considerationsEnvironnementales": "",
        "type": "Marché",
        "acheteur_categorie": "Collectivité",
        "titulaire_categorie": "PME",
    }
]
_PARQUET_PATH = Path(os.path.abspath("tests/test.parquet"))
_DB_PATH = Path(os.path.abspath("decp.duckdb"))

# Schéma déterministe et hors-ligne pour les tests : on pointe le cache sur un
# fixture commité et on désactive la récupération distante.
_SCHEMA_FIXTURE = Path(os.path.abspath("tests/schema.fixture.json"))
os.environ["DATA_SCHEMA_CACHE"] = str(_SCHEMA_FIXTURE)
os.environ.pop("DATA_SCHEMA_PATH", None)


_DB_BACKUP = _DB_PATH.with_suffix(".duckdb.pytest-backup")


def _cleanup_db_artifacts() -> None:
    for artifact in (
        _DB_PATH,
        _DB_PATH.with_suffix(".duckdb.tmp"),
        _DB_PATH.with_suffix(".duckdb.lock"),
    ):
        if artifact.exists():
            artifact.unlink()


def _backup_db() -> None:
    if _DB_PATH.exists():
        _DB_PATH.rename(_DB_BACKUP)


def _restore_db() -> None:
    _cleanup_db_artifacts()
    if _DB_BACKUP.exists():
        _DB_BACKUP.rename(_DB_PATH)


# Runs at conftest import, before test modules import src.db (which builds the
# DuckDB at import time). Guarantees the test parquet exists and the stale DB
# from a previous `python run.py` is wiped so src.db rebuilds from test data.
pl.DataFrame(_TEST_DATA).write_parquet(_PARQUET_PATH)
_backup_db()
_cleanup_db_artifacts()


@pytest.fixture(scope="session", autouse=True)
def test_data():
    yield str(_PARQUET_PATH)
    # Teardown: restore the original DuckDB so the next `python run.py` finds it.
    _restore_db()


def pytest_setup_options():
    """Options Chrome pour les tests d'intégration Selenium.

    dash.testing n'utilise PAS une fixture `chrome_options` (contrairement à
    pytest-selenium) : il appelle ce hook `pytest_setup_options`. C'est donc le
    seul point d'entrée qui a réellement un effet. On force `--headless=new`
    pour qu'aucune fenêtre Chrome ne s'ouvre pendant les tests. Le dossier de
    téléchargement, `--no-sandbox`, `--disable-gpu` et `--disable-dev-shm-usage`
    sont déjà gérés par dash.testing.browser.
    """
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1200,1200")
    return options
