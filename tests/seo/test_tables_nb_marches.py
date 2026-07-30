"""Les tables d'index portent le nombre de marchés par organisme."""


def test_acheteurs_departement_a_nb_marches():
    from src.db import get_cursor

    rows = (
        get_cursor()
        .execute(
            "SELECT acheteur_id, nb_marches FROM acheteurs_departement "
            "WHERE acheteur_id = '123'"
        )
        .fetchall()
    )
    assert rows == [("123", 1)]


def test_titulaires_departement_a_nb_marches():
    from src.db import get_cursor

    rows = (
        get_cursor()
        .execute(
            "SELECT titulaire_id, nb_marches FROM titulaires_departement "
            "WHERE titulaire_id = '345'"
        )
        .fetchall()
    )
    assert rows == [("345", 1)]


def test_une_ligne_par_organisme_et_departement():
    """Le GROUP BY ne doit pas dupliquer les organismes."""
    from src.db import get_cursor

    total, distincts = (
        get_cursor()
        .execute(
            "SELECT COUNT(*), COUNT(DISTINCT (acheteur_id, acheteur_departement_code)) "
            "FROM acheteurs_departement"
        )
        .fetchone()
    )
    assert total == distincts
