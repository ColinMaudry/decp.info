"""Index d'organismes par département, rendus côté serveur."""

import pytest

from src.seo import pagination


@pytest.fixture(scope="module")
def client():
    from src.app import app

    return app.server.test_client()


@pytest.fixture
def departement_76(monkeypatch):
    """3 acheteurs dans un département dédié, sur une base DuckDB en mémoire.

    Le code "76" (Seine-Maritime) est choisi car réellement présent dans
    `data/departements.json` (contrairement à un code arbitraire comme "99",
    que la route rejetterait en 404 faute de correspondance dans
    `DEPARTEMENTS`) et non utilisé par les autres fixtures de la suite.

    La connexion DuckDB du processus est ouverte en lecture seule
    (`src/db.py:218`) : on ne peut donc PAS insérer via `get_cursor()`. On
    substitue le curseur utilisé par les requêtes, pas la base réelle — même
    précédent que `tests/seo/test_tables_nb_marches.py`. La base meurt avec la
    fixture, donc aucun nettoyage à faire.
    """
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE acheteurs_departement ("
        "acheteur_id VARCHAR, acheteur_nom VARCHAR, "
        "acheteur_departement_code VARCHAR, nb_marches BIGINT)"
    )
    for i, nb in enumerate([7, 3, 42]):
        conn.execute(
            "INSERT INTO acheteurs_departement VALUES (?, ?, '76', ?)",
            [f"org-{i}", f"ORGANISME {i}", nb],
        )
    monkeypatch.setattr("src.seo.queries.get_cursor", lambda: conn.cursor())
    yield "76"
    conn.close()


def test_hub_liste_les_departements(client):
    body = client.get("/departements").get_data(as_text=True)
    assert '<a href="/departements/75/acheteurs">' in body
    assert '<a href="/departements/75/titulaires">' in body


def test_index_porte_les_deux_liens_par_organisme(client):
    """Chaque ligne mène à la fiche ET à la liste de marchés."""
    body = client.get("/departements/75/acheteurs").get_data(as_text=True)
    assert '<a href="/acheteurs/123">' in body
    assert '<a href="/acheteurs/123/marches">' in body


def test_index_affiche_le_nombre_de_marches(client):
    body = client.get("/departements/75/acheteurs").get_data(as_text=True)
    assert "1 marché" in body


def test_tri_par_nombre_de_marches_decroissant(client, departement_76):
    body = client.get("/departements/76/acheteurs").get_data(as_text=True)
    assert (
        body.index("ORGANISME 2")
        < body.index("ORGANISME 0")
        < body.index("ORGANISME 1")
    )


def test_pagination_de_l_index(client, departement_76, monkeypatch):
    monkeypatch.setattr(pagination, "PAGE_SIZE", 2)
    page1 = client.get("/departements/76/acheteurs").get_data(as_text=True)
    page2 = client.get("/departements/76/acheteurs?page=2").get_data(as_text=True)
    assert "ORGANISME 2" in page1 and "ORGANISME 1" not in page1
    assert "ORGANISME 1" in page2


def test_departement_inconnu_404(client):
    assert client.get("/departements/zz/acheteurs").status_code == 404


def test_type_inconnu_404(client):
    assert client.get("/departements/75/autre").status_code == 404


@pytest.mark.parametrize("page", ["0", "abc", "-1"])
def test_page_invalide_404(client, page):
    assert client.get(f"/departements/75/acheteurs?page={page}").status_code == 404


def test_page_hors_limites_404(client):
    assert client.get("/departements/75/acheteurs?page=99").status_code == 404


@pytest.fixture
def acheteurs_sans_departement(monkeypatch):
    """2 acheteurs sans département (NULL) et 1 avec un département renseigné.

    Un `WHERE acheteur_departement_code = ?` avec `None` en paramètre ne
    matche jamais NULL en SQL (`x = NULL` s'évalue à faux, jamais à vrai) :
    la requête renverrait alors un total de 0, donc une page vide, donc un
    200 — un simple `assert status_code == 200` resterait donc vert même en
    l'absence du `IS NULL` explicite. Cette fixture peuple une base
    `:memory:` avec deux lignes réellement NULL et une ligne à département
    renseigné, pour que le test associé puisse vérifier la présence des deux
    premières ET l'absence de la troisième — la seule combinaison qui échoue
    à la fois si `IS NULL` est remplacé par `= ?` (plus aucune ligne) et si un
    filtre trop large était utilisé par erreur (toutes les lignes).
    """
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE acheteurs_departement ("
        "acheteur_id VARCHAR, acheteur_nom VARCHAR, "
        "acheteur_departement_code VARCHAR, nb_marches BIGINT)"
    )
    conn.execute(
        "INSERT INTO acheteurs_departement VALUES "
        "('sd-1', 'SANS DEPT UN', NULL, 5), "
        "('sd-2', 'SANS DEPT DEUX', NULL, 2), "
        "('avec-dept', 'AVEC DEPT', '75', 9)"
    )
    monkeypatch.setattr("src.seo.queries.get_cursor", lambda: conn.cursor())
    yield
    conn.close()


def test_segment_non_renseigne_servi(client, acheteurs_sans_departement):
    """Les organismes sans département ont un chemin explorable.

    Voir le docstring de `acheteurs_sans_departement` : c'est l'assertion
    d'absence de « AVEC DEPT » qui fait mordre ce test sur un `= ?` naïf.
    """
    response = client.get("/departements/non-renseigne/acheteurs")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "SANS DEPT UN" in body
    assert "SANS DEPT DEUX" in body
    assert "AVEC DEPT" not in body
