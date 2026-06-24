from dash.testing.composite import DashComposite


def test_tableau_hscroll_bar_present(dash_duo: DashComposite):
    """La barre de défilement est injectée et le conteneur scroll horizontalement."""
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    dash_duo.wait_for_element(".marches_table", timeout=20)
    # Barre injectée par table_hscroll.js
    dash_duo.wait_for_element(".marches_table .dt-hscroll", timeout=10)
    dash_duo.wait_for_element(".marches_table .dt-hscroll-thumb", timeout=5)

    # Le conteneur Dash doit avoir overflow-x:hidden (scroll contenu, pas de scrollbar page)
    container = dash_duo.find_element(".marches_table .dash-spreadsheet-container")
    overflow = container.value_of_css_property("overflow-x")
    assert overflow == "hidden"
