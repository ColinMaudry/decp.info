import time

from dash.testing.composite import DashComposite
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By


def test_tableau_grid_column_width_persists_after_reload(dash_duo: DashComposite):
    """Régression : redimensionner une colonne de l'AG Grid puis recharger la
    page ne doit pas remettre la colonne à sa largeur par défaut.

    persisted_props=["columnState"] (cf. src.figures.ag_grid) est censé
    survivre au rechargement via le localStorage, mais apply_hidden_columns
    régénère columnDefs (avec une largeur par défaut figée, cf.
    src.utils.grid._column_width) à chaque chargement de page, ce qui écrase
    l'état restauré.
    """
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    dash_duo.wait_for_element(".ag-root", timeout=8)
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=8)

    header_cells = ".ag-header-row-column .ag-header-cell"
    headers = dash_duo.driver.find_elements(By.CSS_SELECTOR, header_cells)
    # Le premier en-tête est la colonne "marche" épinglée (pas de resize) ;
    # on redimensionne le deuxième en-tête (première colonne de données).
    target = headers[1]
    handle = target.find_element(By.CLASS_NAME, "ag-header-cell-resize")
    original_width = target.size["width"]

    ActionChains(dash_duo.driver).move_to_element(
        handle
    ).click_and_hold().move_by_offset(120, 0).release().perform()
    time.sleep(1)  # laisse le temps au debounce onColumnResized + persistence local

    resized_width = dash_duo.driver.find_elements(By.CSS_SELECTOR, header_cells)[
        1
    ].size["width"]
    assert resized_width > original_width + 40, (
        "le redimensionnement n'a pas été appliqué, le test ne peut pas vérifier la persistance"
    )

    dash_duo.driver.refresh()
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=8)

    reloaded_width = dash_duo.driver.find_elements(By.CSS_SELECTOR, header_cells)[
        1
    ].size["width"]
    assert reloaded_width == resized_width
