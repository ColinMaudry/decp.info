"""Accord singulier/pluriel pour les libellés générés dynamiquement (#128)."""

import pytest

from src.utils.pluriel import accorder


@pytest.mark.parametrize("n", [0, 1])
def test_singulier_pour_zero_et_un(n):
    assert accorder(n, "marché public", "marchés publics") == "marché public"


def test_pluriel_au_dela_de_un():
    assert accorder(2, "marché public", "marchés publics") == "marchés publics"


def test_pluriel_regulier_par_defaut():
    """Sans forme plurielle explicite, on suffixe un "s" (cas régulier)."""
    assert accorder(5, "acheteur") == "acheteurs"


def test_singulier_sans_forme_plurielle_explicite():
    assert accorder(1, "acheteur") == "acheteur"
