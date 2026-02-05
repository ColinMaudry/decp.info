import datetime
import os

import polars as pl
import pytest
from selenium.webdriver.chrome.options import Options


@pytest.fixture(scope="session", autouse=True)
def test_data():
    data = [
        {
            "uid": "1",
            "id": "1",
            "acheteur_nom": "ACHETEUR 1",
            "acheteur_id": "a1",
            "titulaire_nom": "TITULAIRE 1",
            "titulaire_id": "t1",
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
        }
    ]
    path = "tests/test.parquet"
    path = os.path.abspath(path)
    print(f"Writing test data to: {path}")  # <-- This will show you the real path

    pl.DataFrame(data).write_parquet("tests/test.parquet")
    yield path


def pytest_setup_options():
    options = Options()
    options.add_argument("--window-size=1200,800")
    return options
