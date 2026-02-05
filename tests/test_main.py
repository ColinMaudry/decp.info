from time import sleep

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
        assert (
            result_table.find_element(
                by=By.CSS_SELECTOR, value=f'td[data-dash-column="{org_type}_nom"]'
            ).text
            == name
        ), f"The search result should have the right {org_type} name"


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
        sleep(1)
        filter_input = open_page_and_check_filter_input()
        assert filter_input.get_attribute("value") == "11"
