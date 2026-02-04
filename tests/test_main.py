from dash.testing.composite import DashComposite
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement


def test_001_logo_and_search(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "decp.info", timeout=4)
    assert dash_duo.find_element(".logo > h1").text == "decp.info"
    search_bar: WebElement = dash_duo.find_element("#search")
    search_bar.click()
    search_bar.send_keys("A")
    search_bar.send_keys(Keys.ENTER)

    dash_duo.wait_for_element("#results_acheteur_datatable")
    result_table_acheteurs: WebElement = dash_duo.find_element(
        "#results_acheteur_datatable tbody"
    )

    assert (
        len(result_table_acheteurs.find_elements(by=By.TAG_NAME, value="tr")) == 2
    )  # header row + 1 result
    assert (
        result_table_acheteurs.find_element(
            by=By.CSS_SELECTOR, value='td[data-dash-column="acheteur_nom"]'
        ).text
        == "Acheteur 1"
    )
