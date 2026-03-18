import polars as pl
from dash.testing.composite import DashComposite
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement


def test_001_logo_and_search(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "decp.info", timeout=4)
    assert dash_duo.find_element(".logo > h1").text == "decp.info"

    for org_type in ["acheteur", "titulaire"]:
        name = f"{org_type.upper()} 1"
        search_bar: WebElement = dash_duo.find_element("#search")

        dash_duo.clear_input(search_bar)

        search_bar.send_keys(name)
        search_bar.send_keys(Keys.ENTER)

        dash_duo.wait_for_element(f"#results_{org_type}_datatable", timeout=2)
        result_table: WebElement = dash_duo.find_element(
            f"#results_{org_type}_datatable tbody"
        )

        assert len(result_table.find_elements(by=By.TAG_NAME, value="tr")) == 2, (
            "The search should return only one result"
        )  # header row + 1 result
        assert result_table.find_element(
            by=By.CSS_SELECTOR, value=f'td[data-dash-column="{org_type}_nom"]'
        ).text.startswith(name), (
            f"The search result should have the right {org_type} name"
        )


def test_002_filter_persistence(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "decp.info", timeout=4)

    def open_page_and_check_filter_input():
        dash_duo.wait_for_page(f"{dash_duo.server_url}/{page}")
        filter_input_selector = (
            '.marches_table th[data-dash-column="uid"] input[type="text"]'
        )
        dash_duo.wait_for_element(filter_input_selector, timeout=2)
        _filter_input: WebElement = dash_duo.find_element(filter_input_selector)
        return _filter_input

    for page in ["tableau", "acheteurs/a1", "titulaires/t1"]:
        print("page:", page)
        filter_input = open_page_and_check_filter_input()
        filter_input.send_keys("11")  # a UID that doesn't exist
        filter_input.send_keys(Keys.ENTER)
        filter_input = open_page_and_check_filter_input()
        assert filter_input.get_attribute("value") == "11"


def test_003_tableau_download(dash_duo: DashComposite):
    from pages.acheteur import download_acheteur_data
    from pages.tableau import download_data
    from pages.titulaire import download_titulaire_data
    from src.app import app

    # Juste pour instancier l'app
    print(app.server.name)

    dicts = pl.read_parquet("tests/test.parquet").to_dicts()

    outputs = [
        download_data(1, "", [], None),
        download_acheteur_data(1, dicts, "a1", "2025"),
        download_titulaire_data(1, dicts, "t1", "2025"),
    ]
    for output in outputs:
        assert isinstance(output, dict)
        for f in ["content", "filename", "type", "base64"]:
            assert f in output
        assert isinstance(output["content"], str) and len(output["content"]) > 100
        assert isinstance(output["filename"], str) and output["filename"].startswith(
            "decp_"
        )
        assert output["type"] is None
        assert output["base64"] is True


def test_004_add_links_observatoire_acheteur():
    import polars as pl

    from src.utils import add_links

    dff = pl.DataFrame(
        {
            "acheteur_id": ["a1"],
            "acheteur_nom": ["ACHETEUR 1"],
        }
    )
    result = add_links(dff)
    nom_value = result["acheteur_nom"][0]
    id_value = result["acheteur_id"][0]

    # acheteur_nom should contain detail link + observatoire link
    assert "/acheteurs/a1" in nom_value
    assert "ACHETEUR 1" in nom_value
    assert "/observatoire?acheteur_id=a1" in nom_value
    assert "📊" in nom_value

    # acheteur_id should NOT contain observatoire link
    assert "/observatoire" not in id_value


def test_005_add_links_observatoire_titulaire():
    import polars as pl

    from src.utils import add_links

    dff = pl.DataFrame(
        {
            "titulaire_id": ["t1"],
            "titulaire_nom": ["TITULAIRE 1"],
            "titulaire_typeIdentifiant": ["SIRET"],
        }
    )
    result = add_links(dff)
    nom_value = result["titulaire_nom"][0]
    id_value = result["titulaire_id"][0]

    # titulaire_nom should contain detail link + observatoire link
    assert "/titulaires/t1" in nom_value
    assert "TITULAIRE 1" in nom_value
    assert "/observatoire?titulaire_id=t1" in nom_value
    assert "📊" in nom_value

    # titulaire_id should NOT contain observatoire link
    assert "/observatoire" not in id_value


def test_006_observatoire_url_to_input(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "decp.info", timeout=4)

    # Navigate to observatoire with acheteur_id query param
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire?acheteur_id=a1")
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)

    import time

    time.sleep(1)  # Allow callback chain to complete

    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    assert acheteur_input.get_attribute("value") == "a1", (
        "acheteur_id input should be populated from URL param"
    )


def test_007_observatoire_share_url(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "decp.info", timeout=4)

    # Navigate to observatoire with acheteur_id query param
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire?acheteur_id=a1")
    dash_duo.wait_for_element("#observatoire-share-url", timeout=4)

    import time

    time.sleep(1)  # Allow callback chain to complete

    share_url_input = dash_duo.find_element("#observatoire-share-url")
    share_url_value = share_url_input.get_attribute("value")

    assert "acheteur_id=a1" in share_url_value, (
        f"Share URL should contain acheteur_id param, got: {share_url_value}"
    )


def test_008_search_to_observatoire(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "decp.info", timeout=4)

    # Search for an acheteur
    search_bar = dash_duo.find_element("#search")
    search_bar.send_keys("ACHETEUR 1")
    search_bar.send_keys(Keys.ENTER)

    dash_duo.wait_for_element("#results_acheteur_datatable", timeout=2)

    # Find the observatoire link in acheteur_nom column
    observatoire_link = dash_duo.find_element(
        '#results_acheteur_datatable td[data-dash-column="acheteur_nom"] a[href*="observatoire"]'
    )
    assert "📊" in observatoire_link.text

    # Click the observatoire link
    observatoire_link.click()

    # Wait for observatoire page to load
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)

    import time

    time.sleep(1)  # Allow callback chain to complete

    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    assert acheteur_input.get_attribute("value") == "a1", (
        "acheteur_id input should be populated after navigating from search"
    )
