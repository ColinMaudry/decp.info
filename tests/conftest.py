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


def _cleanup_db_artifacts() -> None:
    for artifact in (
        _DB_PATH,
        _DB_PATH.with_suffix(".duckdb.tmp"),
        _DB_PATH.with_suffix(".duckdb.lock"),
    ):
        if artifact.exists():
            artifact.unlink()


# Runs at conftest import, before test modules import src.db (which builds the
# DuckDB at import time). Guarantees the test parquet exists and the stale DB
# from a previous `python run.py` is wiped so src.db rebuilds from test data.
pl.DataFrame(_TEST_DATA).write_parquet(_PARQUET_PATH)
_cleanup_db_artifacts()


@pytest.fixture(scope="session", autouse=True)
def test_data():
    yield str(_PARQUET_PATH)
    # Teardown: remove the test DuckDB so the next `python run.py` rebuilds
    # from decp_prod.parquet.
    _cleanup_db_artifacts()


def pytest_setup_options():
    options = Options()
    options.add_argument("--window-size=1200,1200 ")
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": "/home/colin/git/decp.info",
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )
    return options
