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


def test_saved_views_items_build_clickable_entries():
    items = ui.saved_views_items(
        [_view(1, "Vue A", "filtres=a"), _view(2, "Vue B", "tris=b")]
    )
    assert len(items) == 2
    assert items[0].id == {"type": "saved-view-item", "index": 1}
    assert items[0].children == "Vue A"
    assert items[1].id == {"type": "saved-view-item", "index": 2}


def test_views_table_empty_state():
    out = ui.views_table([])
    # un Div non vide (message d'état) sans item de suppression
    assert out is not None


def test_views_table_lists_views():
    out = ui.views_table([_view(1, "Vue A", "filtres=a")])
    text = str(out)
    assert "Vue A" in text


def test_slugify_accents_spaces_case():
    assert ui.slugify("Mes Marchés 2024") == "mes-marches-2024"


def test_slugify_special_chars_collapse_and_trim():
    assert ui.slugify("  Éà!! ---  test__ok  ") == "ea-test-ok"


def test_slugify_never_contains_underscore():
    assert "_" not in ui.slugify("a_b c")


def test_slugify_empty():
    assert ui.slugify("") == ""
    assert ui.slugify(None) == ""


def test_build_view_url_dev_domain(monkeypatch):
    # DOMAIN_NAME est résolu à l'import ; on patche l'attribut du module ui.
    monkeypatch.setattr(ui, "DOMAIN_NAME", "test.colibre.fr")
    url = ui.build_view_url("Mes Marchés", "abc123")
    assert url == "https://test.colibre.fr/tableau?vue=mes-marches_abc123"


def test_build_view_url_empty_slug_omits_prefix(monkeypatch):
    monkeypatch.setattr(ui, "DOMAIN_NAME", "test.colibre.fr")
    url = ui.build_view_url("!!!", "abc123")
    assert url == "https://test.colibre.fr/tableau?vue=abc123"


def test_token_from_vue_param():
    assert ui.token_from_vue_param("mes-marches-2024_abc123") == "abc123"
    assert ui.token_from_vue_param("zzz_abc123") == "abc123"
    assert ui.token_from_vue_param("abc123") == "abc123"
    assert ui.token_from_vue_param("") is None
    assert ui.token_from_vue_param(None) is None
