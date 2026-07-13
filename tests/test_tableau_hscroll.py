from dash.testing.composite import DashComposite


def test_acheteur_ag_grid_horizontal_scroll_present(dash_duo: DashComposite):
    """La grille AG Grid de la fiche acheteur affiche son propre défilement
    horizontal natif (alwaysShowHorizontalScroll=True, cf. ag_grid() dans
    src/figures.py), avec le jeu complet de colonnes DECP. Remplace l'ancien
    test basé sur dash_table.DataTable + table_hscroll.js, disparu de
    /acheteurs et /titulaires depuis la migration AG Grid (#41,
    src/utils/entity_grid.py)."""
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/acheteurs/123")

    # Attendre que la grille AG Grid soit montée puis ait rendu des lignes.
    dash_duo.wait_for_element("#acheteur-grid-container .ag-root", timeout=20)
    dash_duo.wait_for_element(
        "#acheteur-grid-container .ag-center-cols-container .ag-row", timeout=10
    )

    # Le viewport de défilement horizontal natif d'AG Grid doit être présent
    # (scopé au conteneur de la fiche acheteur pour ne pas matcher une autre
    # grille éventuellement présente sur la page, ex. top 10).
    dash_duo.wait_for_element(
        "#acheteur-grid-container div.ag-body-horizontal-scroll-viewport",
        timeout=10,
    )
