"""Le mode observatoire de bout en bout, avec une session réellement abonnée.

Couvre la chaîne que les tests unitaires ne voient pas : interrupteur →
callback clientside → callback serveur → cards. La session est ouverte par le
vrai formulaire de connexion, et `TOUS_ABONNES` ouvre les fonctionnalités
d'abonné sans passer par la base d'abonnements — comme en production pendant
la période d'accès gratuit.
"""

import time

import pytest
from dash.testing.composite import DashComposite
from selenium.webdriver.common.by import By

EMAIL = "mode-observatoire@test.local"
MOT_DE_PASSE = "motdepasse-de-test-137"


@pytest.fixture
def compte_abonne(monkeypatch):
    from werkzeug.security import generate_password_hash

    from src.auth import db as auth_db

    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)

    row = auth_db.get_user_by_email(EMAIL)
    if row is None:
        user_id = auth_db.create_user(EMAIL, generate_password_hash(MOT_DE_PASSE))
    else:
        user_id = row["id"]
        auth_db.update_password_hash(user_id, generate_password_hash(MOT_DE_PASSE))
    auth_db.set_email_verified(user_id)
    return user_id


def _se_connecter(dash_duo: DashComposite):
    dash_duo.wait_for_page(f"{dash_duo.server_url}/connexion")
    dash_duo.wait_for_element("input[name='email']", timeout=8)
    dash_duo.driver.find_element(By.CSS_SELECTOR, "input[name='email']").send_keys(
        EMAIL
    )
    champ_mdp = dash_duo.driver.find_element(By.CSS_SELECTOR, "input[name='password']")
    champ_mdp.send_keys(MOT_DE_PASSE)
    champ_mdp.submit()
    time.sleep(2)


def _ouvrir_le_tableau(dash_duo: DashComposite):
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    dash_duo.wait_for_element(".ag-root", timeout=10)
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=10)


def test_linterrupteur_souvre_a_une_session_abonnee(
    dash_duo: DashComposite, compte_abonne
):
    from src.app import app

    dash_duo.start_server(app)
    _se_connecter(dash_duo)
    _ouvrir_le_tableau(dash_duo)

    interrupteur = dash_duo.driver.find_element(By.ID, "tableau-mode-observatoire")

    assert interrupteur.is_enabled()


def test_la_bascule_affiche_les_cards_du_filtre_courant(
    dash_duo: DashComposite, compte_abonne
):
    from src.app import app

    dash_duo.start_server(app)
    _se_connecter(dash_duo)
    _ouvrir_le_tableau(dash_duo)
    driver = dash_duo.driver

    champ = driver.find_element(
        By.CSS_SELECTOR, ".ag-floating-filter-input input[aria-label*='acheteur']"
    )
    champ.send_keys("ACHETEUR")
    time.sleep(2)

    driver.find_element(By.ID, "tableau-mode-observatoire").click()
    dash_duo.wait_for_element("#tableau-observatoire-cards .card", timeout=15)

    cards = driver.find_element(By.ID, "tableau-observatoire-cards")
    titres = [t.text for t in cards.find_elements(By.CSS_SELECTOR, ".card-title")]

    assert "Résumé" in titres
    # Le corps de la grille a bien laissé la place, l'en-tête est resté.
    assert not driver.find_element(By.CSS_SELECTOR, ".ag-body").is_displayed()
    assert driver.find_element(By.CSS_SELECTOR, ".ag-header").is_displayed()


def test_sans_filtre_la_bascule_invite_a_en_poser_un(
    dash_duo: DashComposite, compte_abonne
):
    from src.app import app

    dash_duo.start_server(app)
    _se_connecter(dash_duo)
    _ouvrir_le_tableau(dash_duo)
    driver = dash_duo.driver

    driver.find_element(By.ID, "tableau-mode-observatoire").click()
    time.sleep(3)

    cards = driver.find_element(By.ID, "tableau-observatoire-cards")

    assert "Appliquez au moins un filtre" in cards.text


@pytest.fixture
def compte_sans_abonnement(monkeypatch, compte_abonne):
    """Le même compte vérifié et connecté, mais sans accès d'abonné : c'est
    bien TOUS_ABONNES (ou un abonnement) qui ouvre le mode, pas le simple fait
    d'avoir un compte."""
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    monkeypatch.setattr("src.subscriptions.db.has_access", lambda _uid: False)
    return compte_abonne


def test_un_compte_sans_acces_garde_linterrupteur_ferme(
    dash_duo: DashComposite, compte_sans_abonnement
):
    from src.app import app

    dash_duo.start_server(app)
    _se_connecter(dash_duo)
    _ouvrir_le_tableau(dash_duo)

    interrupteur = dash_duo.driver.find_element(By.ID, "tableau-mode-observatoire")
    enveloppe = dash_duo.driver.find_element(By.ID, "tableau-mode-observatoire-wrapper")

    assert not interrupteur.is_enabled()
    assert (
        enveloppe.get_attribute("title") == "Fonctionnalité accessible en vous abonnant"
    )
