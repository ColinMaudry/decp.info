from unittest.mock import patch

import pytest

import src.app  # noqa: F401  # instancie l'app → register_page() des pages
from src.pages.tableau import get_rows_tableau, reset_view
from src.utils import grid as grid_module
from src.utils.grid import export_dataframe, fetch_grid_page, grid_column_defs


@pytest.fixture(scope="module")
def flask_app():
    """Minimal Flask app with SimpleCache so @cache.memoize() works in tests
    (même pattern que tests/test_table.py)."""
    from flask import Flask

    from src.utils.cache import cache

    app = Flask(__name__)
    cache.init_app(app, config={"CACHE_TYPE": "SimpleCache"})
    return app


@pytest.fixture(autouse=True)
def reset_cache(flask_app):
    from src.utils.cache import cache

    with flask_app.app_context():
        try:
            cache.clear()
        except (RuntimeError, AttributeError):
            pass
        yield


def test_column_defs_have_field_and_filter():
    defs = grid_column_defs(hidden_columns=[])
    by_field = {d["field"]: d for d in defs}
    assert "objet" in by_field
    # filtre texte par défaut
    assert by_field["objet"]["filter"] == "agTextColumnFilter"
    # montant est numérique
    assert by_field["montant"]["filter"] == "agNumberColumnFilter"
    # headerTooltip présent (définition de colonne)
    assert "headerTooltip" in by_field["objet"]


def test_column_defs_hidden_flag():
    defs = grid_column_defs(hidden_columns=["objet"])
    by_field = {d["field"]: d for d in defs}
    assert by_field["objet"]["hide"] is True


def test_fetch_grid_page_returns_rows_and_count():
    rows, total = fetch_grid_page(None, None, 0, 20)
    assert isinstance(rows, list)
    assert isinstance(total, int)
    assert total >= len(rows)
    if rows:
        # postprocess_page ajoute une colonne 'marche' avec un lien
        assert "marche" in rows[0]


def test_fetch_grid_page_filter_reduces_count():
    _, total_all = fetch_grid_page(None, None, 0, 1)
    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "zzzzzznope"}}
    rows, total_filtered = fetch_grid_page(fm, None, 0, 20)
    assert total_filtered <= total_all
    assert rows == [] and total_filtered == 0


def test_fetch_grid_page_offset_slicing():
    rows, _ = fetch_grid_page(None, None, 0, 5)
    assert len(rows) <= 5


def test_export_dataframe_excludes_hidden_columns():
    df = export_dataframe(None, None, hidden_columns=["objet"])
    assert "objet" not in df.columns


def test_export_dataframe_applies_filter():
    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "zzzzzznope"}}
    df = export_dataframe(fm, None, hidden_columns=[])
    assert df.height == 0


def test_get_rows_tableau_tracks_search_once_per_filter_not_per_scroll_block():
    """Régression revue finale #41 : AG Grid envoie une getRowsRequest par bloc
    de défilement infini, avec le même filterModel tant que le filtre ne
    change pas. track_search ne doit être appelé qu'une fois par filtre (au
    premier bloc, startRow == 0), pas une fois par bloc défilé."""
    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "route"}}
    with patch("src.pages.tableau.track_search") as mocked:
        get_rows_tableau({"filterModel": fm, "startRow": 0, "endRow": 100})
        get_rows_tableau({"filterModel": fm, "startRow": 100, "endRow": 200})
        get_rows_tableau({"filterModel": fm, "startRow": 200, "endRow": 300})
    mocked.assert_called_once()


def test_fetch_grid_page_caches_count_across_scroll_blocks(flask_app, monkeypatch):
    """Régression revue finale #41 : count_marches ne doit être appelé qu'une
    fois pour des blocs de défilement successifs partageant le même
    where_sql/params (même filtre, start_row différent)."""
    call_count = {"n": 0}
    real_count_marches = grid_module.count_marches

    def counting_count_marches(where_sql, params):
        call_count["n"] += 1
        return real_count_marches(where_sql, params)

    monkeypatch.setattr(grid_module, "count_marches", counting_count_marches)

    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "route"}}
    with flask_app.app_context():
        _, total1 = fetch_grid_page(fm, None, 0, 20)
        _, total2 = fetch_grid_page(fm, None, 20, 40)
        _, total3 = fetch_grid_page(fm, None, 40, 60)

    assert call_count["n"] == 1
    assert total1 == total2 == total3


def test_reset_view_clears_filter_and_sort():
    """Régression : le bouton Réinitialiser ('Supprime tous les filtres et les
    tris') ne remettait à zéro que filterModel, jamais le tri (#41)."""
    filter_model, reset_column_state = reset_view(1)
    assert filter_model == {}
    assert reset_column_state is True
