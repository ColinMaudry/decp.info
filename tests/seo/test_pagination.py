"""Arithmétique de pagination des pages SEO."""

import pytest

from src.seo.pagination import PAGE_SIZE, offset, page_count, parse_page


def test_page_absente_vaut_un():
    assert parse_page(None) == 1


def test_page_valide():
    assert parse_page("3") == 3


@pytest.mark.parametrize("brut", ["0", "-1", "abc", "", "1.5", " 2"])
def test_page_invalide_leve_valueerror(brut):
    with pytest.raises(ValueError):
        parse_page(brut)


def test_page_count_arrondit_au_superieur():
    assert page_count(PAGE_SIZE + 1) == 2
    assert page_count(PAGE_SIZE) == 1


def test_page_count_vaut_au_moins_un_si_vide():
    assert page_count(0) == 1


def test_offset():
    assert offset(1) == 0
    assert offset(3) == 2 * PAGE_SIZE
