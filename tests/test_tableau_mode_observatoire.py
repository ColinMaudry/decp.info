"""Mode observatoire de la page Tableau (issue #137).

Un interrupteur bascule l'affichage des lignes de la grille vers les cards de
l'observatoire, alimentées par les filtres AG Grid en cours.
"""

import pytest


@pytest.fixture
def layout_str():
    from src.app import app  # noqa: F401  (instancie Dash avant les pages)
    from src.pages import tableau

    return str(tableau.layout)


def test_la_barre_doutils_porte_linterrupteur(layout_str):
    assert "tableau-mode-observatoire" in layout_str


def test_linterrupteur_est_encadre_des_deux_icones(layout_str):
    assert "☰" in layout_str
    assert "📊" in layout_str


def test_linterrupteur_annonce_quil_est_reserve_aux_abonnes(layout_str):
    assert "Fonctionnalité accessible en vous abonnant" in layout_str


def test_le_layout_porte_la_modale_montants(layout_str):
    """La card Résumé rend un « ? » qui ouvre montant-modal via un callback
    pattern-matching global : sans la modale dans ce layout, Dash lèverait une
    erreur d'Output introuvable au clic."""
    assert "montant-modal" in layout_str


def test_le_conteneur_des_cards_suit_la_grille(layout_str):
    assert "tableau-observatoire-cards" in layout_str


@pytest.fixture
def tableau_abonne(monkeypatch):
    """Page Tableau vue par une personne abonnée."""
    from src.app import app  # noqa: F401
    from src.pages import tableau

    monkeypatch.setattr(tableau, "current_user_has_subscription", lambda: True)
    return tableau


FILTRE_ACHETEUR = {
    "acheteur_nom": {"filterType": "text", "type": "contains", "filter": "ACHETEUR"}
}


def test_mode_inactif_masque_les_cards_sans_les_recalculer(tableau_abonne):
    from dash import no_update

    children, classe = tableau_abonne.update_mode_observatoire_cards(
        False, FILTRE_ACHETEUR
    )

    # Les cards restent montées : repasser en mode observatoire ne relance
    # aucune requête tant que le filtre n'a pas changé.
    assert children is no_update
    assert "d-none" in classe


def test_sans_filtre_le_mode_invite_a_en_appliquer_un(tableau_abonne):
    children, classe = tableau_abonne.update_mode_observatoire_cards(True, None)

    assert "Appliquez au moins un filtre" in str(children)
    assert "d-none" not in classe


def test_avec_un_filtre_les_cards_de_lobservatoire_sont_affichees(tableau_abonne):
    children, classe = tableau_abonne.update_mode_observatoire_cards(
        True, FILTRE_ACHETEUR
    )

    assert "d-none" not in classe
    # Les mêmes cards que /observatoire : la card « Résumé » en tête.
    assert "Résumé" in str(children)


def test_le_filtre_de_la_grille_restreint_bien_les_cards(tableau_abonne):
    """Un filtre qui ne retient aucune ligne ne doit pas produire les mêmes
    cards qu'un filtre qui retient tout : c'est la preuve que le filterModel
    est bien transmis à la requête."""
    aucun_resultat = {
        "acheteur_nom": {
            "filterType": "text",
            "type": "contains",
            "filter": "zzzzz-inexistant",
        }
    }

    avec, _ = tableau_abonne.update_mode_observatoire_cards(True, FILTRE_ACHETEUR)
    sans, _ = tableau_abonne.update_mode_observatoire_cards(True, aucun_resultat)

    assert str(avec) != str(sans)


def test_le_mode_est_refuse_sans_abonnement(monkeypatch):
    from src.app import app  # noqa: F401
    from src.pages import tableau

    monkeypatch.setattr(tableau, "current_user_has_subscription", lambda: False)

    children, _classe = tableau.update_mode_observatoire_cards(True, FILTRE_ACHETEUR)

    assert "Résumé" not in str(children)
    assert "abonnant" in str(children)


def test_linterrupteur_est_actif_pour_un_abonne(tableau_abonne):
    desactive, _title = tableau_abonne.toggle_mode_observatoire_control("/tableau")

    assert desactive is False


def test_linterrupteur_est_desactive_sans_abonnement(monkeypatch):
    from src.app import app  # noqa: F401
    from src.pages import tableau

    monkeypatch.setattr(tableau, "current_user_has_subscription", lambda: False)

    desactive, title = tableau.toggle_mode_observatoire_control("/tableau")

    assert desactive is True
    assert title == "Fonctionnalité accessible en vous abonnant"
