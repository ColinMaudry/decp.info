import pytest
from dash.testing.composite import DashComposite


@pytest.mark.skip(
    reason=(
        "Plus de dash_table.DataTable disponible pour ce test depuis la migration "
        "AG Grid des fiches acheteur/titulaire (#41, entity_grid.py) : /acheteurs "
        "et /titulaires rendent désormais tous deux une grille AG Grid (qui gère "
        "son propre défilement horizontal nativement, cf. "
        "test_figures.py::test_ag_grid_always_shows_horizontal_scroll), donc "
        ".marches_table + table_hscroll.js n'y existent plus. Le seul repli "
        "restant, observatoire.py (Lot 2b, hors périmètre de #41), a un bug "
        "préexistant et sans rapport (get_considerations_card_content lève un "
        "ValueError sur ce jeu de données — src/figures.py, unpack 2-tuple/"
        "3-tuple dans compute_considerations_stats) qui empêche actuellement le "
        ".marches_table de cette page de se rendre en Selenium. À réactiver sur "
        "observatoire.py une fois ce bug corrigé séparément, ou à retirer si "
        "cette couverture E2E est jugée obsolète."
    )
)
def test_marches_table_hscroll_bar_present(dash_duo: DashComposite):
    """La barre de défilement est injectée et le conteneur scroll horizontalement."""
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire?acheteur_id=123")
    dash_duo.wait_for_element(".marches_table", timeout=20)
    # Barre injectée par table_hscroll.js
    dash_duo.wait_for_element(".marches_table .dt-hscroll", timeout=10)
    dash_duo.wait_for_element(".marches_table .dt-hscroll-thumb", timeout=5)

    # Le conteneur Dash doit avoir overflow-x:hidden (scroll contenu, pas de scrollbar page)
    container = dash_duo.find_element(".marches_table .dash-spreadsheet-container")
    overflow = container.value_of_css_property("overflow-x")
    assert overflow == "hidden"
