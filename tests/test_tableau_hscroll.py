from dash.testing.composite import DashComposite


def test_tableau_hscroll_bar_present(dash_duo: DashComposite):
    """La barre miroir est injectée et l'en-tête est collant sur /tableau."""
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    dash_duo.wait_for_element(".marches_table", timeout=20)
    # Barre miroir injectée par table_hscroll.js
    dash_duo.wait_for_element(".marches_table .dt-hscroll", timeout=10)

    header = dash_duo.find_element(".marches_table th.dash-header")
    position = header.value_of_css_property("position")
    assert position == "sticky"
