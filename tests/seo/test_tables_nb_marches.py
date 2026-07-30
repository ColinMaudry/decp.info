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
    """Le GROUP BY ne doit pas dupliquer les organismes.

    Ce test s'appuie sur les données de tests/conftest.py, qui ne contiennent
    qu'une seule ligne : il ne peut donc pas, à lui seul, distinguer une
    implémentation correcte d'un bug de duplication par graphie de nom. Voir
    les tests ci-dessous, qui exercent directement la logique SQL du
    regroupement contre une table `decp` synthétique pour combler ce trou.
    """
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


def _build_decp_synthetique(conn):
    """Crée une table `decp` minimale dans une connexion DuckDB en mémoire.

    Ne touche pas à tests/conftest.py::_TEST_DATA : cette fixture est locale
    au test et sert uniquement à exercer SQL_ACHETEURS_DEPARTEMENT /
    SQL_TITULAIRES_DEPARTEMENT, indépendamment du jeu de données partagé par
    le reste de la suite.

    Organismes construits :
    - acheteur_id "A1" / titulaire_id "T1" : 2 marchés (uid m1, m2), portant
      chacun une graphie différente de la raison sociale -> doit produire
      UNE SEULE ligne après regroupement, avec nb_marches = 2.
    - acheteur_id "B1" : 2 marchés (uid m4, m5), même nb_marches que A1, pour
      vérifier le critère de tri secondaire (identifiant) en cas d'égalité.
    - acheteur_id "A2" / titulaire_id "T2" : 1 marché (uid m3), pour
      vérifier le tri principal (nb_marches DESC).
    """
    conn.execute(
        "CREATE TABLE decp AS SELECT * FROM (VALUES "
        "('m1', 'A1', 'Acheteur Un', '75', 'T1', 'Titulaire Un', '35'),"
        "('m2', 'A1', 'ACHETEUR UN (bis)', '75', 'T1', 'TITULAIRE UN (bis)', '35'),"
        "('m3', 'A2', 'Acheteur Deux', '75', 'T2', 'Titulaire Deux', '35'),"
        "('m4', 'B1', 'Acheteur B1', '75', 'T3', 'Titulaire B1', '35'),"
        "('m5', 'B1', 'Acheteur B1', '75', 'T3', 'Titulaire B1', '35')"
        ") AS t(uid, acheteur_id, acheteur_nom, acheteur_departement_code, "
        "titulaire_id, titulaire_nom, titulaire_departement_code)"
    )


def test_group_by_dedoublonne_les_graphies_de_nom_acheteur():
    """Un même acheteur_id avec plusieurs graphies de nom ne fait qu'une ligne.

    Ce test échoue si SQL_ACHETEURS_DEPARTEMENT est remplacé par
    `SELECT DISTINCT acheteur_id, acheteur_nom, acheteur_departement_code` :
    ce DISTINCT produirait alors 2 lignes pour A1 (une par graphie), au lieu
    d'une seule avec nb_marches = 2.
    """
    import duckdb

    from src.db import SQL_ACHETEURS_DEPARTEMENT

    with duckdb.connect(":memory:") as conn:
        _build_decp_synthetique(conn)
        conn.execute(SQL_ACHETEURS_DEPARTEMENT)

        rows = conn.execute(
            "SELECT acheteur_id, nb_marches FROM acheteurs_departement "
            "WHERE acheteur_id = 'A1'"
        ).fetchall()
        assert rows == [("A1", 2)]


def test_group_by_dedoublonne_les_graphies_de_nom_titulaire():
    """Même vérification que ci-dessus, côté titulaires."""
    import duckdb

    from src.db import SQL_TITULAIRES_DEPARTEMENT

    with duckdb.connect(":memory:") as conn:
        _build_decp_synthetique(conn)
        conn.execute(SQL_TITULAIRES_DEPARTEMENT)

        rows = conn.execute(
            "SELECT titulaire_id, nb_marches FROM titulaires_departement "
            "WHERE titulaire_id = 'T1'"
        ).fetchall()
        assert rows == [("T1", 2)]


def test_ordre_nb_marches_desc_puis_identifiant():
    """La table est triée par nb_marches décroissant, puis identifiant.

    A1 et B1 ont le même nb_marches (2) : le tri doit les départager par
    acheteur_id croissant ('A1' avant 'B1'). A2, avec un seul marché, doit
    arriver en dernier.
    """
    import duckdb

    from src.db import SQL_ACHETEURS_DEPARTEMENT

    with duckdb.connect(":memory:") as conn:
        _build_decp_synthetique(conn)
        conn.execute(SQL_ACHETEURS_DEPARTEMENT)

        rows = conn.execute(
            "SELECT acheteur_id, nb_marches FROM acheteurs_departement"
        ).fetchall()
        assert rows == [("A1", 2), ("B1", 2), ("A2", 1)]
