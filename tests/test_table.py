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


def test_normalize_sort_by_handles_empty():
    from src.utils.table import normalize_sort_by

    assert normalize_sort_by(None) == ()
    assert normalize_sort_by([]) == ()


def test_normalize_sort_by_returns_hashable_tuple():
    from src.utils.table import normalize_sort_by

    sort_by = [
        {"column_id": "montant", "direction": "desc"},
        {"column_id": "dateNotification", "direction": "asc"},
    ]
    key = normalize_sort_by(sort_by)

    assert key == (("montant", "desc"), ("dateNotification", "asc"))
    # Must be hashable so that flask-caching can build a cache key from it
    hash(key)


def test_normalize_sort_by_preserves_order():
    """Order matters for sort: [A, B] != [B, A]."""
    from src.utils.table import normalize_sort_by

    a_then_b = normalize_sort_by(
        [{"column_id": "a", "direction": "asc"}, {"column_id": "b", "direction": "asc"}]
    )
    b_then_a = normalize_sort_by(
        [{"column_id": "b", "direction": "asc"}, {"column_id": "a", "direction": "asc"}]
    )
    assert a_then_b != b_then_a


@pytest.fixture(scope="module")
def flask_app():
    """Minimal Flask app with SimpleCache so @cache.memoize() works in tests."""
    from flask import Flask

    from src.cache import cache

    app = Flask(__name__)
    cache.init_app(app, config={"CACHE_TYPE": "SimpleCache"})
    return app


@pytest.fixture(autouse=True)
def reset_cache(flask_app):
    """Ensure the flask-caching backend is empty between tests so that
    cache-hit assertions are meaningful. Falls back to no-op when no
    Flask app context is active (NullCache)."""
    from src.cache import cache

    with flask_app.app_context():
        try:
            cache.clear()
        except (RuntimeError, AttributeError):
            # No app context — cache is NullCache, nothing to clear
            pass
        yield


def test_load_filter_sort_postprocess_returns_dataframe(
    flask_app, monkeypatch, sample_lff
):
    from src.utils import table

    monkeypatch.setattr(table, "query_marches", lambda: sample_lff.collect())

    with flask_app.app_context():
        df = table._load_filter_sort_postprocess(filter_query=None, sort_by_key=())

    assert isinstance(df, pl.DataFrame)
    assert df.height == 1
    # All values must be strings after post-processing
    for col in df.columns:
        assert df.schema[col] == pl.String


def test_load_filter_sort_postprocess_applies_filter(
    flask_app, monkeypatch, sample_lff
):
    from src.utils import table

    monkeypatch.setattr(table, "query_marches", lambda: sample_lff.collect())

    with flask_app.app_context():
        df = table._load_filter_sort_postprocess(
            filter_query="{objet} icontains travaux", sort_by_key=()
        )
        assert df.height == 1

        df_empty = table._load_filter_sort_postprocess(
            filter_query="{objet} icontains nonexistent", sort_by_key=()
        )
        assert df_empty.height == 0


def test_load_filter_sort_postprocess_adds_links(flask_app, monkeypatch, sample_lff):
    from src.utils import table

    monkeypatch.setattr(table, "query_marches", lambda: sample_lff.collect())

    with flask_app.app_context():
        df = table._load_filter_sort_postprocess(filter_query=None, sort_by_key=())
    # add_links injects an <a href> wrapper around uid, acheteur_nom, titulaire_nom
    assert "<a href" in df["uid"][0]
    assert "<a href" in df["acheteur_nom"][0]
    assert "<a href" in df["titulaire_nom"][0]
