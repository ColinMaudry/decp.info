import polars as pl
import pytest


@pytest.fixture
def sample_lff():
    """Small LazyFrame with the columns needed by add_links / format_values."""
    return pl.LazyFrame(
        [
            {
                "uid": "u1",
                "id": "u1",
                "acheteur_id": "12345678900011",
                "acheteur_nom": "Mairie de Test",
                "titulaire_id": "98765432100022",
                "titulaire_nom": "Entreprise Test",
                "titulaire_typeIdentifiant": "SIRET",
                "objet": "Travaux divers",
                "montant": 12500.0,
                "dateNotification": "2025-03-15",
                "codeCPV": "45000000",
                "dureeRestanteMois": 6,
                "titulaire_distance": 42.0,
            }
        ]
    )


def test_table_module_imports():
    from src.utils import table

    assert hasattr(table, "prepare_table_data")


def test_filter_table_data_does_not_call_track_search(monkeypatch, sample_lff):
    from src.utils import table

    calls = []
    monkeypatch.setattr(table, "track_search", lambda *a, **kw: calls.append(a))

    result = table.filter_table_data(
        sample_lff, "{objet} icontains travaux", "tableau"
    ).collect()

    assert calls == []
    assert result.height == 1
