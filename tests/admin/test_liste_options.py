"""Le menu déroulant de la page admin doit proposer toutes les tables.

Test au niveau composant plutôt que Selenium : on inspecte le layout rendu,
ce qui suffit à vérifier la liste des options et évite un navigateur.
"""


def _select_options(layout):
    """Retourne les options du dbc.Select du layout, quelle que soit sa place."""
    if getattr(layout, "id", None) == "admin-table-select":
        return [opt["value"] for opt in layout.options]
    for child in getattr(layout, "children", None) or []:
        found = _select_options(child)
        if found is not None:
            return found
    return None


def test_dropdown_lists_every_table(users_db_path, monkeypatch):
    import src.app  # noqa: F401 — register_page() exige une app instanciée
    from src.admin import tables
    from src.pages.admin import liste

    monkeypatch.setattr(liste, "is_admin", lambda: True)

    options = _select_options(liste.layout())

    assert options is not None, "sélecteur de table introuvable dans le layout"
    assert set(options) == set(tables.all_tables())
    assert "mcp_usage" in options
    assert "oauth_tokens" in options
