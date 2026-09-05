"""Le sélecteur de colonnes du Tableau, de bout en bout.

Aucun test ne le couvrait, alors que l'issue #139 a déplacé le moment où ses
cases sont alimentées (ouverture de la modale, et non plus toute écriture du
store). Ce fichier vérifie que le parcours complet fonctionne toujours.
"""

import time

from dash.testing.composite import DashComposite
from selenium.webdriver.common.by import By

CASES = "#tableau_column_list input[type='checkbox']"


def _entetes_de_la_grille(dash_duo) -> set[str]:
    cellules = dash_duo.driver.find_elements(
        By.CSS_SELECTOR, "#tableau_grid .ag-header-cell-text"
    )
    return {c.text for c in cellules if c.text}


def _ouvrir_la_modale(dash_duo: DashComposite):
    dash_duo.driver.find_element(By.ID, "tableau_columns_open").click()
    dash_duo.wait_for_element(CASES, timeout=8)
    time.sleep(1)  # laisse le callback d'ouverture peupler les cases


def test_ouvrir_la_modale_coche_les_colonnes_affichees(dash_duo: DashComposite):
    """Le cœur du changement de #139 : les cases sont peuplées à l'ouverture.
    Si elles restaient vides, l'utilisateur croirait n'avoir aucune colonne
    affichée et décocherait dans le vide."""
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=10)

    _ouvrir_la_modale(dash_duo)

    cochees = [
        c
        for c in dash_duo.driver.find_elements(By.CSS_SELECTOR, CASES)
        if c.is_selected()
    ]

    assert cochees, "aucune case cochée : les cases n'ont pas été alimentées"


def test_decocher_une_colonne_la_retire_de_la_grille(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=10)
    avant = _entetes_de_la_grille(dash_duo)
    assert avant, "aucun en-tête lu avant l'action"

    _ouvrir_la_modale(dash_duo)
    driver = dash_duo.driver

    cible = None
    for case in driver.find_elements(By.CSS_SELECTOR, CASES):
        if not case.is_selected():
            continue
        ligne = case.find_element(By.XPATH, "./ancestor::tr")
        nom = ligne.find_element(By.CSS_SELECTOR, "td[data-dash-column='name']").text
        if nom in avant:
            cible = (case, nom)
            break
    assert cible is not None, f"aucune case cochée ne correspond aux en-têtes {avant}"

    case, nom = cible
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", case)
    case.click()
    time.sleep(1.5)
    driver.find_element(By.ID, "tableau_columns_close").click()
    time.sleep(1.5)

    assert nom not in _entetes_de_la_grille(dash_duo), (
        f"la colonne « {nom} » est toujours affichée après avoir été décochée"
    )
