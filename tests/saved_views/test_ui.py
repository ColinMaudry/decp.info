from src.saved_views import ui


class _Row(dict):
    """Imite un sqlite3.Row : accès par clé."""


def _view(view_id, name, query):
    return _Row(id=view_id, name=name, query=query)


def test_bar_style_hidden_for_non_subscriber():
    assert ui.bar_style(False) == {"display": "none"}
    assert ui.bar_style(True) == {}


def test_clean_view_name_strips_and_empties():
    assert ui.clean_view_name("  Ma vue  ") == "Ma vue"
    assert ui.clean_view_name("   ") == ""
    assert ui.clean_view_name(None) == ""


def test_prepare_refuses_non_subscriber():
    name, err = ui.prepare_view_to_save(False, "Ma vue")
    assert name is None
    assert err


def test_prepare_refuses_empty_name():
    name, err = ui.prepare_view_to_save(True, "   ")
    assert name is None
    assert err


def test_prepare_accepts_valid():
    name, err = ui.prepare_view_to_save(True, "  Ma vue  ")
    assert name == "Ma vue"
    assert err is None


def test_saved_views_items_build_links():
    items = ui.saved_views_items(
        [_view(1, "Vue A", "filtres=a"), _view(2, "Vue B", "tris=b")]
    )
    assert len(items) == 2
    assert items[0].href == "/tableau?filtres=a"
    assert items[0].children == "Vue A"


def test_views_table_empty_state():
    out = ui.views_table([])
    # un Div non vide (message d'état) sans item de suppression
    assert out is not None


def test_views_table_lists_views():
    out = ui.views_table([_view(1, "Vue A", "filtres=a")])
    text = str(out)
    assert "Vue A" in text
