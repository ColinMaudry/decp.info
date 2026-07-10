from src.utils.grid import fetch_grid_page


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
