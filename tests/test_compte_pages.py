from dash.testing.composite import DashComposite


def test_compte_redirects_anonymous_to_login(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.driver.get(dash_duo.server_url + "/compte/admin")
    dash_duo.wait_for_text_to_equal("h2", "Connexion", timeout=8)
    assert "/connexion" in dash_duo.driver.current_url


def test_compte_root_redirects_to_admin(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.driver.get(dash_duo.server_url + "/compte")
    # /compte (anonyme) → /compte/admin → /connexion
    dash_duo.wait_for_text_to_equal("h2", "Connexion", timeout=8)
