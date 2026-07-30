"""Listes de marchés par organisme, rendues côté serveur.

Deux familles de tests :

- ceux qui se contentent de la donnée existante (acheteur "123" / uid "1" /
  "Objet test", titulaire "345") passent par la vraie base DuckDB, sans rien
  monkeypatcher ;
- ceux qui ont besoin de plusieurs marchés pour exercer la pagination
  monkeypatchent `src.seo.queries.get_cursor` vers une base DuckDB `:memory:`
  peuplée par la fixture, plutôt que d'écrire dans la base process-wide.

Cette dernière est ouverte en lecture seule (`src/db.py`, pour permettre à
plusieurs workers gunicorn de la partager en concurrence) : `get_cursor()` ne
peut donc pas servir à insérer des données de test. Comme `queries.py` fait
`from src.db import get_cursor`, le nom est lié dans l'espace de noms de
`queries` : monkeypatcher `src.seo.queries.get_cursor` intercepte bien les
appels faits par les routes, sans toucher à `src/db.py`. Même précédent que
`tests/seo/test_tables_nb_marches.py`, étendu au cas des routes HTTP.
"""

import duckdb
import pytest

from src.seo import pagination


@pytest.fixture(scope="module")
def client():
    from src.app import app

    return app.server.test_client()


@pytest.fixture
def acheteur_a_5_marches(monkeypatch):
    """Un acheteur "999" à 5 marchés, servi depuis une base DuckDB en mémoire.

    La base meurt avec la fixture (pas de DELETE de nettoyage nécessaire),
    ce qui est plus sûr qu'écrire puis nettoyer dans la base partagée par le
    reste de la suite.
    """
    mem = duckdb.connect(":memory:")
    mem.execute(
        "CREATE TABLE acheteurs_marches (uid VARCHAR, objet VARCHAR, acheteur_id VARCHAR)"
    )
    mem.execute(
        "CREATE TABLE acheteurs_departement ("
        "acheteur_id VARCHAR, acheteur_nom VARCHAR, "
        "acheteur_departement_code VARCHAR, nb_marches BIGINT)"
    )
    # Insérées dans un ordre délibérément différent du tri alphabétique attendu :
    # une table neuve jamais modifiée restitue sinon l'ordre de scan physique,
    # qui coïnciderait par hasard avec l'ordre alphabétique et rendrait
    # test_pagination_deterministe incapable de distinguer un ORDER BY présent
    # d'un ORDER BY absent.
    for i in (3, 1, 4, 0, 2):
        mem.execute(
            "INSERT INTO acheteurs_marches (uid, objet, acheteur_id) VALUES (?, ?, ?)",
            [f"uid-{i:02d}", f"Objet {i}", "999"],
        )
    mem.execute(
        "INSERT INTO acheteurs_departement "
        "(acheteur_id, acheteur_nom, acheteur_departement_code, nb_marches) "
        "VALUES ('999', 'ACHETEUR 999', '75', 5)"
    )
    monkeypatch.setattr("src.seo.queries.get_cursor", lambda: mem.cursor())
    yield "999"
    mem.close()


@pytest.fixture
def acheteur_sans_marches(monkeypatch):
    """Un acheteur "998" connu mais sans aucun marché.

    Couvre le cas limite du brief : organisme sans marché -> 200 avec
    « Aucun résultat. », pas un 404.
    """
    mem = duckdb.connect(":memory:")
    mem.execute(
        "CREATE TABLE acheteurs_marches (uid VARCHAR, objet VARCHAR, acheteur_id VARCHAR)"
    )
    mem.execute(
        "CREATE TABLE acheteurs_departement ("
        "acheteur_id VARCHAR, acheteur_nom VARCHAR, "
        "acheteur_departement_code VARCHAR, nb_marches BIGINT)"
    )
    mem.execute(
        "INSERT INTO acheteurs_departement "
        "(acheteur_id, acheteur_nom, acheteur_departement_code, nb_marches) "
        "VALUES ('998', 'ACHETEUR 998', '75', 0)"
    )
    monkeypatch.setattr("src.seo.queries.get_cursor", lambda: mem.cursor())
    yield "998"
    mem.close()


# --- Famille 1 : donnée existante, vraie base, sans monkeypatch --------------


def test_liste_rendue_cote_serveur(client):
    """Le HTML servi contient les liens, sans exécution de JavaScript."""
    body = client.get("/acheteurs/123/marches").get_data(as_text=True)
    assert '<a href="/marches/1">' in body
    assert "Objet test" in body


def test_lien_de_retour_vers_la_fiche(client):
    body = client.get("/acheteurs/123/marches").get_data(as_text=True)
    assert '<a href="/acheteurs/123">' in body


def test_organisme_inconnu_404(client):
    assert client.get("/acheteurs/inexistant/marches").status_code == 404


@pytest.mark.parametrize("page", ["0", "abc", "-1"])
def test_page_invalide_404(client, page):
    assert client.get(f"/acheteurs/123/marches?page={page}").status_code == 404


def test_page_hors_limites_404(client):
    assert client.get("/acheteurs/123/marches?page=99").status_code == 404


def test_titulaire_aussi_servi(client):
    body = client.get("/titulaires/345/marches").get_data(as_text=True)
    assert '<a href="/marches/1">' in body


def test_accord_singulier_sur_un_seul_marche(client):
    """ "Les 1 marchés publics" était le défaut relevé en revue (#128) :
    accord exact au singulier, sans "Les" ni pluriel fautif."""
    import re

    body = client.get("/acheteurs/123/marches").get_data(as_text=True)
    titre = re.findall(r"<title>(.*?)</title>", body)[0]
    assert titre == "1 marché public attribué par ACHETEUR 1 | colibre"
    assert "1 marché public attribué par ACHETEUR 1." in body


# --- Famille 2 : pagination multi-pages, base en mémoire monkeypatchée ------


def test_organisme_sans_marche_rend_200_et_aucun_resultat(
    client, acheteur_sans_marches
):
    response = client.get("/acheteurs/998/marches")
    assert response.status_code == 200
    assert "Aucun résultat." in response.get_data(as_text=True)


def test_accord_pluriel_et_mot_cle_marches_publics(client, acheteur_a_5_marches):
    import re

    body = client.get("/acheteurs/999/marches").get_data(as_text=True)
    titre = re.findall(r"<title>(.*?)</title>", body)[0]
    assert titre == "5 marchés publics attribués par ACHETEUR 999 | colibre"


def test_canonical_auto_referent_sur_page_2(client, acheteur_a_5_marches, monkeypatch):
    """La balise canonical elle-même doit porter la query string de pagination.

    `"/acheteurs/999/marches?page=2" in body` resterait vrai à cause du LIEN
    DE PAGINATION (`<a class="page-link" href="...">`), même si la balise
    canonical pointait ailleurs (ex. `request.base_url` seul, sans la query
    string). On extrait donc précisément la valeur de l'attribut `href` de la
    balise `rel="canonical"`.
    """
    import re

    monkeypatch.setattr(pagination, "PAGE_SIZE", 2)
    body = client.get("/acheteurs/999/marches?page=2").get_data(as_text=True)
    canonicals = re.findall(r'rel="canonical" href="(.*?)"', body)
    assert len(canonicals) == 1
    assert canonicals[0].endswith("/acheteurs/999/marches?page=2")


def test_pagination_deterministe(client, acheteur_a_5_marches, monkeypatch):
    """Chaque page rend exactement les uid attendus, dans l'ordre attendu.

    La fixture insère les marchés dans le désordre (uid-03, uid-01, uid-04,
    uid-00, uid-02) précisément pour que ce test ne puisse pas passer « par
    coïncidence » avec l'ordre de scan physique de la table. C'est le défaut
    que la pagination introduirait sans ORDER BY : un même marché sur deux
    pages, un autre sur aucune, ou un ordre non déterministe.
    """
    import re

    monkeypatch.setattr(pagination, "PAGE_SIZE", 2)
    pages = {}
    vus = []
    for page in (1, 2, 3):
        body = client.get(f"/acheteurs/999/marches?page={page}").get_data(as_text=True)
        uids = re.findall(r'href="/marches/(uid-\d+)"', body)
        pages[page] = uids
        vus.extend(uids)

    assert pages[1] == ["uid-00", "uid-01"]
    assert pages[2] == ["uid-02", "uid-03"]
    assert pages[3] == ["uid-04"]
    # Garde en plus l'assertion sur l'union : aucun doublon, couverture complète.
    assert len(vus) == len(set(vus)) == 5
