from src.utils.grid import fetch_grid_page, grid_column_defs


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
