"""Le mode observatoire vu par le navigateur : le corps de la grille disparaît,
son en-tête reste visible et actionnable.

Les assertions sur le texte de style.css ne prouvent pas que les sélecteurs
visent quelque chose. Ici on applique la classe et on regarde le DOM réel.
"""

import time

from dash.testing.composite import DashComposite
from selenium.webdriver.common.by import By


def _charger_le_tableau(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    dash_duo.wait_for_element(".ag-root", timeout=8)
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=8)


def test_le_corps_de_la_grille_est_visible_hors_mode_observatoire(
    dash_duo: DashComposite,
):
    """Contrôle négatif : sans la classe, le corps est bien affiché — sinon le
    test suivant passerait pour de mauvaises raisons."""
    _charger_le_tableau(dash_duo)

    corps = dash_duo.driver.find_element(By.CSS_SELECTOR, ".ag-body")

    assert corps.is_displayed()


def test_la_classe_masque_le_corps_et_conserve_len_tete(dash_duo: DashComposite):
    _charger_le_tableau(dash_duo)
    driver = dash_duo.driver
    enveloppe = driver.find_element(By.ID, "tableau-grid-wrapper")
    hauteur_avec_lignes = enveloppe.size["height"]

    driver.execute_script(
        "document.getElementById('tableau-grid-wrapper')"
        ".className = 'marches_table mode-observatoire';"
    )
    time.sleep(0.3)

    assert not driver.find_element(By.CSS_SELECTOR, ".ag-body").is_displayed()
    assert driver.find_element(By.CSS_SELECTOR, ".ag-header").is_displayed()
    # Les filtres flottants restent atteignables pour affiner la sélection.
    assert driver.find_element(By.CSS_SELECTOR, ".ag-floating-filter").is_displayed()
    assert enveloppe.size["height"] < hauteur_avec_lignes


def test_lentete_reste_defilable_horizontalement(dash_duo: DashComposite):
    """Les colonnes débordent de la largeur de l'écran même avec le choix par
    défaut. Sans barre de défilement, les filtres des colonnes de droite
    deviendraient inatteignables en mode observatoire — or c'est justement là
    qu'on veut pouvoir affiner sans quitter le mode."""
    _charger_le_tableau(dash_duo)
    driver = dash_duo.driver
    driver.execute_script(
        "document.getElementById('tableau-grid-wrapper')"
        ".className = 'marches_table mode-observatoire';"
    )
    time.sleep(0.3)

    entete = driver.find_element(By.CSS_SELECTOR, ".ag-header-viewport")
    deborde = driver.execute_script(
        "return arguments[0].scrollWidth > arguments[0].clientWidth;", entete
    )
    assert deborde, "l'en-tête ne déborde pas : le test ne prouverait rien"

    barre = driver.find_element(By.CSS_SELECTOR, ".ag-body-horizontal-scroll")
    assert barre.is_displayed()

    # La barre pilote bien le défilement de l'en-tête.
    driver.execute_script(
        "document.querySelector('.ag-body-horizontal-scroll-viewport')"
        ".scrollLeft = 300;"
    )
    time.sleep(0.4)
    assert driver.execute_script("return arguments[0].scrollLeft;", entete) > 0
