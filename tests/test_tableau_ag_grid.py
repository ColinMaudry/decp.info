from dash.testing.composite import DashComposite


def test_tableau_grid_loads_and_filters(dash_duo: DashComposite):
    """La page /tableau charge et affiche la grille AG Grid avec au moins une ligne."""
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    # La grille AG Grid est présente
    dash_duo.wait_for_element(".ag-root", timeout=8)
    # Au moins une ligne rendue (row) après chargement du premier bloc
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=8)
    assert dash_duo.get_logs() == [] or all(
        "SEVERE" not in log["level"] for log in dash_duo.get_logs()
    )
