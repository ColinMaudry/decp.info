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

    result = table.filter_table_data(sample_lff, "{objet} icontains travaux").collect()

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

    from utils.cache import cache

    app = Flask(__name__)
    cache.init_app(app, config={"CACHE_TYPE": "SimpleCache"})
    return app


@pytest.fixture(autouse=True)
def reset_cache(flask_app):
    """Ensure the flask-caching backend is empty between tests so that
    cache-hit assertions are meaningful. Falls back to no-op when no
    Flask app context is active (NullCache)."""
    from utils.cache import cache

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


def test_prepare_table_data_returns_expected_tuple(monkeypatch, flask_app, sample_lff):
    from src.utils import table

    monkeypatch.setattr(table, "query_marches", lambda: sample_lff.collect())

    with flask_app.app_context():
        result = table.prepare_table_data(
            data=None,
            data_timestamp=5,
            filter_query=None,
            page_current=0,
            page_size=20,
            sort_by=[],
            source_table="tableau",
        )

    # Same arity as before: 9 outputs
    assert len(result) == 9
    dicts, columns, tooltip, ts, nb_rows, dl_disabled, dl_text, dl_title, cleanup = (
        result
    )
    assert isinstance(dicts, list)
    assert ts == 6  # data_timestamp + 1 must still increment
    assert "1 lignes" in nb_rows


def test_prepare_table_data_calls_track_search_on_filter(
    monkeypatch, flask_app, sample_lff
):
    from src.utils import table

    calls = []
    monkeypatch.setattr(table, "query_marches", lambda: sample_lff.collect())
    monkeypatch.setattr(table, "track_search", lambda *a, **kw: calls.append(a))

    with flask_app.app_context():
        table.prepare_table_data(
            data=None,
            data_timestamp=0,
            filter_query="{objet} icontains travaux",
            page_current=0,
            page_size=20,
            sort_by=[],
            source_table="tableau",
        )

    assert calls == [("{objet} icontains travaux", "tableau")]


def test_prepare_table_data_paginates_without_recomputing(
    monkeypatch, flask_app, sample_lff
):
    """Two calls with same filter+sort but different pages must invoke
    the inner heavy work only once."""
    from src.utils import table

    call_count = {"n": 0}
    real_query = sample_lff.collect()

    def counting_query():
        call_count["n"] += 1
        return real_query

    monkeypatch.setattr(table, "query_marches", counting_query)

    with flask_app.app_context():
        # First call: cache miss
        table.prepare_table_data(
            data=None,
            data_timestamp=0,
            filter_query=None,
            page_current=0,
            page_size=10,
            sort_by=[],
            source_table="tableau",
        )
        first_count = call_count["n"]

        # Second call, different page: cache hit, query_marches must NOT fire again
        table.prepare_table_data(
            data=None,
            data_timestamp=0,
            filter_query=None,
            page_current=1,
            page_size=10,
            sort_by=[],
            source_table="tableau",
        )

    assert call_count["n"] == first_count, (
        "query_marches was called again — pagination triggered cache miss"
    )


def test_prepare_table_data_cleanup_trigger_for_non_tableau(
    monkeypatch, flask_app, sample_lff
):
    """Non-tableau pages still get a fresh uuid trigger, not no_update."""
    from dash import no_update

    from src.utils import table

    monkeypatch.setattr(table, "query_marches", lambda: sample_lff.collect())

    with flask_app.app_context():
        result = table.prepare_table_data(
            data=None,
            data_timestamp=0,
            filter_query="{objet} icontains travaux",
            page_current=0,
            page_size=20,
            sort_by=[],
            source_table="acheteur",
        )

    cleanup = result[8]
    assert cleanup is not no_update
    assert isinstance(cleanup, str)
    assert len(cleanup) >= 32  # uuid4 hex string


def test_prepare_table_data_with_external_data_does_not_use_cache(
    monkeypatch, flask_app, sample_lff
):
    """When a caller passes data (acheteur/titulaire/observatoire path),
    bypass the memoized helper entirely."""
    from src.utils import table

    sentinel = {"called": False}

    def should_not_be_called(*a, **kw):
        sentinel["called"] = True
        raise AssertionError("Memoized helper must not be called when data is provided")

    monkeypatch.setattr(table, "_load_filter_sort_postprocess", should_not_be_called)

    with flask_app.app_context():
        table.prepare_table_data(
            data=sample_lff,  # external LazyFrame
            data_timestamp=0,
            filter_query=None,
            page_current=0,
            page_size=20,
            sort_by=[],
            source_table="acheteur",
        )

    assert sentinel["called"] is False


def test_postprocess_page_produces_same_result_as_full_then_slice(
    flask_app, sample_lff
):
    """Post-traiter 20 lignes doit donner le même résultat que post-traiter
    l'ensemble puis slicer."""
    from src.utils import table

    full = sample_lff.collect()
    with flask_app.app_context():
        via_full = table.table_postprocess(full.lazy()).slice(0, 1)
        via_page = table.postprocess_page(full.slice(0, 1))
    assert via_full.columns == via_page.columns
    for col in via_full.columns:
        assert via_full[col].to_list() == via_page[col].to_list()
