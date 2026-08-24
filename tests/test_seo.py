"""Tests SEO : robots.txt, index de sitemaps, sous-sitemaps, canonical.

Utilisent le test client Flask (pas de navigateur) : `src.app` initialise le
cache au moment de l'import, donc les fonctions memoizées du sitemap marchent.
Les données de test (tests/conftest.py) contiennent acheteur_id="123" et
titulaire_id="345".
"""

import pytest


@pytest.fixture(scope="module")
def client():
    from src.app import app

    return app.server.test_client()


def test_robots_prod_declares_sitemap():
    from src.app import _build_robots_txt

    body = _build_robots_txt(development=False)
    assert "Sitemap: https://colibre.fr/sitemap.xml" in body
    assert "User-agent: *\nAllow: /" in body
    assert "meta-externalagent" in body


def test_robots_hors_prod_interdit_tout():
    from src.app import _build_robots_txt

    body = _build_robots_txt(development=True)
    assert "User-agent: *\nDisallow: /" in body
    assert "Allow: /" not in body
    assert "Sitemap:" not in body


def test_robots_route_suit_l_environnement(client):
    """La suite tourne avec DEVELOPMENT=true (pyproject.toml) : variante bloquée."""
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "User-agent: *\nDisallow: /" in body
    assert "Sitemap:" not in body


def test_sitemap_index_lists_children(client):
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<sitemapindex" in body
    assert "https://colibre.fr/sitemap-pages.xml" in body
    assert "https://colibre.fr/sitemap-acheteurs-1.xml" in body
    assert "https://colibre.fr/sitemap-titulaires-1.xml" in body


def test_sitemap_pages_lists_static_pages(client):
    resp = client.get("/sitemap-pages.xml")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<urlset" in body
    assert "<loc>https://colibre.fr/</loc>" in body
    assert "https://colibre.fr/observatoire" in body


def test_sitemap_pages_inclut_les_sous_pages_projet(client):
    """Les sous-pages « Le projet » sont découvertes dans le registre Dash."""
    body = client.get("/sitemap-pages.xml").get_data(as_text=True)
    for path in ("/projet/presentation", "/projet/donnees", "/projet/contact"):
        assert f"<loc>https://colibre.fr{path}</loc>" in body


def test_sitemap_pages_exclut_la_redirection_projet(client):
    """`/projet` est une redirection JS sans contenu : hors sitemap."""
    body = client.get("/sitemap-pages.xml").get_data(as_text=True)
    assert "<loc>https://colibre.fr/projet</loc>" not in body


def test_sitemap_couvre_toutes_les_pages_publiques(client):
    """Filet : une nouvelle page doit rejoindre le sitemap ou les exclusions.

    Évite qu'une page ajoutée hors des `AUTO_PREFIXES` soit oubliée en silence.
    """
    from dash import page_registry

    from src.utils.sitemap import is_non_indexable, static_pages

    couvertes = set(static_pages())
    oubliees = {
        page["path"]
        for page in page_registry.values()
        if not page.get("path_template")
        and page["path"] not in couvertes
        and not is_non_indexable(page["path"])
    }
    assert not oubliees, f"pages ni indexées ni exclues : {sorted(oubliees)}"


def test_sitemap_acheteurs_lists_org_urls(client):
    resp = client.get("/sitemap-acheteurs-1.xml")
    assert resp.status_code == 200
    assert "https://colibre.fr/acheteurs/123" in resp.get_data(as_text=True)


def test_sitemap_titulaires_lists_org_urls(client):
    resp = client.get("/sitemap-titulaires-1.xml")
    assert resp.status_code == 200
    assert "https://colibre.fr/titulaires/345" in resp.get_data(as_text=True)


def test_sitemap_page_out_of_range_is_404(client):
    assert client.get("/sitemap-acheteurs-99.xml").status_code == 404


def test_sitemap_unknown_segment_is_404(client):
    assert client.get("/sitemap-marches-1.xml").status_code == 404


def test_matomo_absent_des_pages_dash_pendant_les_tests(client):
    """MATOMO_TRACKING_ENABLED=false pendant les tests (pyproject.toml) :
    le traqueur ne doit tourner ni en CI ni en dev."""
    body = client.get("/tableau").get_data(as_text=True)
    assert "trackPageView" not in body


def test_matomo_absent_des_pages_seo_ssr_pendant_les_tests(client):
    body = client.get("/departements").get_data(as_text=True)
    assert "trackPageView" not in body


def test_matomo_present_sur_une_page_seo_ssr_quand_active(client, monkeypatch):
    """Le hub /departements était tracké avant l'introduction des pages SEO
    SSR (#128) : ce test garantit qu'il l'est de nouveau une fois le
    traqueur activé, via le même fragment que les pages Dash."""
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")
    body = client.get("/departements").get_data(as_text=True)
    assert "trackPageView" in body


def test_index_has_canonical_link(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'rel="canonical"' in resp.get_data(as_text=True)


def test_index_has_static_social_tags(client):
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    assert 'property="og:site_name" content="colibre"' in body
    assert 'property="og:locale" content="fr_FR"' in body


def test_index_has_per_request_og_url(client):
    resp = client.get("/tableau")
    body = resp.get_data(as_text=True)
    assert 'property="og:url" content="http://localhost/tableau"' in body


def test_make_org_jsonld_reuses_supplied_annuaire_data():
    from src.utils.seo import make_org_jsonld

    fake = {
        "matching_etablissements": [
            {
                "code_postal": "75001",
                "libelle_commune": "Paris",
                "adresse": "1 rue de Paris 75001 Paris",
            }
        ]
    }
    result = make_org_jsonld(
        "21750001500010", "acheteur", org_name="Mairie de Paris", annuaire_data=fake
    )
    assert result["name"] == "Mairie de Paris"
    assert result["address"]["postalCode"] == "75001"
    assert isinstance(result["address"], dict)


def test_sitemap_index_reference_l_arbre(client):
    body = client.get("/sitemap.xml").get_data(as_text=True)
    assert "https://colibre.fr/sitemap-arbre.xml" in body


def test_sitemap_arbre_liste_le_hub_et_les_index(client):
    body = client.get("/sitemap-arbre.xml").get_data(as_text=True)
    assert "<loc>https://colibre.fr/departements</loc>" in body
    assert "<loc>https://colibre.fr/departements/75/acheteurs</loc>" in body


@pytest.fixture
def departement_75_trois_acheteurs(monkeypatch):
    """3 acheteurs dans le département "75", sur une base à part.

    Le conftest partagé n'en fournit qu'un seul, donc un total de 1 : avec
    `PAGE_SIZE=1`, `page_count(1)` vaut déjà 1, la boucle de pagination de
    `_arbre_locs` ne serait jamais exercée et un oubli du `for n in
    range(...)` resterait invisible. 3 acheteurs forcent 3 pages avec
    `PAGE_SIZE=1`.
    """
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE acheteurs_departement ("
        "acheteur_id VARCHAR, acheteur_nom VARCHAR, "
        "acheteur_departement_code VARCHAR, nb_marches BIGINT)"
    )
    for i in range(3):
        conn.execute(
            "INSERT INTO acheteurs_departement VALUES (?, ?, '75', 1)",
            [f"a-{i}", f"ACHETEUR {i}"],
        )
    conn.execute(
        "CREATE TABLE titulaires_departement ("
        "titulaire_id VARCHAR, titulaire_nom VARCHAR, "
        "titulaire_departement_code VARCHAR, nb_marches BIGINT)"
    )
    monkeypatch.setattr("src.db.get_cursor", lambda: conn.cursor())
    yield
    conn.close()


def test_sitemap_arbre_declare_chaque_page_paginee(
    monkeypatch, departement_75_trois_acheteurs
):
    """Un département de plus d'une page déclare chacune de ses pages.

    On appelle `_arbre_locs.uncached` : la fonction est mémoïsée, donc un appel
    par la route renverrait un résultat calculé avec l'ancien PAGE_SIZE.
    """
    from src.seo import pagination
    from src.utils.sitemap import _arbre_locs

    monkeypatch.setattr(pagination, "PAGE_SIZE", 1)
    locs = _arbre_locs.uncached()
    assert "/departements" in locs
    assert "/departements/75/acheteurs" in locs
    assert "/departements/75/acheteurs?page=2" in locs
    assert "/departements/75/acheteurs?page=3" in locs


@pytest.fixture
def organismes_sans_departement(monkeypatch):
    """Un acheteur et un titulaire sans département (NULL), sur une base à part.

    Le conftest partagé ne fournit qu'un acheteur au code "75" et un
    titulaire au code "35" : sans cette fixture, aucune ligne NULL n'existe
    et `_arbre_locs` ne produirait jamais de segment `non-renseigne`, quelle
    que soit la justesse de l'implémentation — le test serait rouge pour de
    mauvaises raisons. On substitue le curseur (la connexion réelle est en
    lecture seule), comme `tests/seo/test_index_departements.py`.
    """
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE acheteurs_departement ("
        "acheteur_id VARCHAR, acheteur_nom VARCHAR, "
        "acheteur_departement_code VARCHAR, nb_marches BIGINT)"
    )
    conn.execute(
        "INSERT INTO acheteurs_departement VALUES ('a-1', 'SANS DEPT', NULL, 3)"
    )
    conn.execute(
        "CREATE TABLE titulaires_departement ("
        "titulaire_id VARCHAR, titulaire_nom VARCHAR, "
        "titulaire_departement_code VARCHAR, nb_marches BIGINT)"
    )
    conn.execute(
        "INSERT INTO titulaires_departement VALUES ('t-1', 'SANS DEPT', NULL, 2)"
    )
    monkeypatch.setattr("src.db.get_cursor", lambda: conn.cursor())
    yield
    conn.close()


def test_sitemap_arbre_couvre_les_organismes_sans_departement(
    client, organismes_sans_departement
):
    """`client` force l'import de `src.app` (donc de `src.utils.data`, qui
    construit `DF_ACHETEURS`/`DF_TITULAIRES` via `get_cursor()` à l'import)
    AVANT le monkeypatch de la fixture : sinon, exécuté seul, ce test ferait
    passer ce chargement à travers le faux curseur et casserait sur un import
    tardif, indépendamment du code sous test (voir
    `test_sitemap_arbre_dedoublonne_les_locs`)."""
    from src.utils.sitemap import _arbre_locs

    locs = _arbre_locs.uncached()
    assert any("non-renseigne" in loc for loc in locs)


@pytest.fixture
def organisme_code_departement_inconnu(monkeypatch):
    """Un acheteur dont le code département ("999") n'existe pas dans
    `data/departements.json`.

    Anomalie de données volontaire : elle ne doit produire ni une URL sous son
    propre code (`index_departement` 404 sur tout code absent de
    `DEPARTEMENTS`, donc une telle URL ne mènerait qu'à un 404), ni être
    rangée sous "non-renseigne" — segment réservé aux organismes SANS code
    département (NULL), pas aux codes inconnus du dictionnaire.
    """
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE acheteurs_departement ("
        "acheteur_id VARCHAR, acheteur_nom VARCHAR, "
        "acheteur_departement_code VARCHAR, nb_marches BIGINT)"
    )
    conn.execute(
        "INSERT INTO acheteurs_departement VALUES ('a-1', 'CODE INCONNU', '999', 3)"
    )
    conn.execute(
        "CREATE TABLE titulaires_departement ("
        "titulaire_id VARCHAR, titulaire_nom VARCHAR, "
        "titulaire_departement_code VARCHAR, nb_marches BIGINT)"
    )
    monkeypatch.setattr("src.db.get_cursor", lambda: conn.cursor())
    yield
    conn.close()


def test_sitemap_arbre_n_assimile_pas_un_code_inconnu_a_non_renseigne(
    client, organisme_code_departement_inconnu
):
    """`client` force l'import de `src.app` (donc de `src.utils.data`, qui
    construit `DF_ACHETEURS`/`DF_TITULAIRES` via `get_cursor()` à l'import)
    AVANT le monkeypatch de la fixture : sinon, exécuté seul, ce test ferait
    passer ce chargement à travers le faux curseur et casserait sur un import
    tardif, indépendamment du code sous test (voir
    `test_sitemap_arbre_dedoublonne_les_locs`)."""
    from src.utils.sitemap import _arbre_locs

    locs = _arbre_locs.uncached()
    assert not any("999" in loc for loc in locs)
    assert not any("non-renseigne" in loc for loc in locs)


class _CurseurQuiDuplique:
    """Simule une requête qui renverrait deux fois la même ligne groupée.

    Le vrai `GROUP BY 1` de `_arbre_locs` ne peut pas produire un tel
    résultat aujourd'hui : cette fausse implémentation de curseur sert
    uniquement à vérifier que `_arbre_locs` dédoublonne bien ses URLs quelle
    que soit leur origine, pas à reproduire un bug SQL existant.
    """

    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_args, **_kwargs):
        return self

    def fetchall(self):
        return self._rows


def test_sitemap_arbre_dedoublonne_les_locs(client, monkeypatch):
    """`client` force l'import de `src.app` (donc de `src.utils.data`, qui
    construit `DF_ACHETEURS`/`DF_TITULAIRES` via `get_cursor()` à l'import)
    AVANT le monkeypatch ci-dessous : sinon, exécuté seul, ce test ferait
    passer ce chargement à travers le faux curseur et casserait sur un import
    tardif, indépendamment du code sous test.
    """
    from src.utils.sitemap import _arbre_locs

    # Même code renvoyé deux fois pour chaque table interrogée : sans
    # dédoublonnage, la même URL de segment apparaîtrait deux fois.
    monkeypatch.setattr(
        "src.db.get_cursor", lambda: _CurseurQuiDuplique([("75", 3), ("75", 3)])
    )
    locs = _arbre_locs.uncached()
    assert locs.count("/departements/75/acheteurs") == 1
    assert locs.count("/departements/75/titulaires") == 1
    assert len(locs) == len(set(locs))


def test_sitemap_arbre_ne_contient_pas_les_listes_de_marches(client):
    """Les listes de marchés sont atteignables depuis les index, pas déclarées.

    Un `assert "/marches" not in body` sur `/sitemap-pages.xml` serait vrai
    quel que soit le code de cette tâche : cette route ne liste jamais de
    marchés. C'est `/sitemap-arbre.xml`, produit par `_arbre_locs`, qu'il
    faut vérifier.
    """
    body = client.get("/sitemap-arbre.xml").get_data(as_text=True)
    assert "/marches" not in body


def test_make_org_jsonld_empty_matching_etablissements_returns_empty_dict():
    from src.utils.seo import make_org_jsonld

    result = make_org_jsonld(
        "21750001500010",
        "acheteur",
        org_name="X",
        annuaire_data={"matching_etablissements": []},
    )
    assert result == {}


def test_make_org_jsonld_none_annuaire_data_returns_empty_dict():
    from src.utils.seo import make_org_jsonld

    result = make_org_jsonld(
        "21750001500010", "acheteur", org_name="X", annuaire_data=None
    )
    assert result == {}


def test_title_servi_contient_le_nom_de_l_organisme(client):
    """Le <title> est le signal principal pour une requête « nom d'organisme »."""
    import re

    from src.utils.data import DF_ACHETEURS

    org_id = DF_ACHETEURS.item(0, "acheteur_id")
    nom = DF_ACHETEURS.item(0, "acheteur_nom")
    body = client.get(f"/acheteurs/{org_id}").get_data(as_text=True)
    titre = re.findall(r"<title>(.*?)</title>", body)[0]
    assert nom in titre


def test_resolve_title_chemin_inconnu_renvoie_none():
    """`resolve_title` sur un chemin hors registre Dash : cas réellement « hors page connue ».

    Un chemin inconnu passé à `client.get` est intercepté 404 par
    `src.not_found` avant même d'atteindre `interpolate_index` : un test HTTP
    ne peut donc pas exercer ce cas, seul un appel direct à `resolve_title` le
    peut.
    """
    from src.utils.page_meta import resolve_title

    assert resolve_title("/ce-chemin-n-existe-pas-du-tout") is None


def test_title_page_statique_prend_le_titre_declare(client):
    """La page d'accueil a un titre statique (non callable) déclaré dans register_page.

    Un simple "le <title> n'est pas vide" resterait vrai même sans le
    correctif (app.title="Colibre" est déjà non vide) : on vérifie ici la
    valeur exacte du titre déclaré par la page, qui ne peut être posée que par
    la résolution serveur ajoutée dans cette tâche.
    """
    import re

    body = client.get("/").get_data(as_text=True)
    titre = re.findall(r"<title>(.*?)</title>", body)[0]
    # L'apostrophe est échappée en entité HTML par _escape (markupsafe).
    assert titre == "Outils pour l&#39;exploration des marchés publics | colibre"


def test_descriptions_distinctes_entre_deux_acheteurs(client):
    """Deux acheteurs doivent avoir des descriptions différentes.

    Comparer un acheteur à un titulaire (deux gabarits de page différents)
    serait toujours vrai : chaque `register_page` déclare une description
    statique différente ("cet acheteur" vs "ce titulaire"), qu'elle soit
    dynamique ou non. Comparer deux instances du MÊME gabarit (un acheteur
    réel et un identifiant inconnu) exerce réellement `get_description`.
    """
    import re

    def description(url):
        body = client.get(url).get_data(as_text=True)
        return re.findall(r'<meta name="description" content="(.*?)"', body)[0]

    assert description("/acheteurs/123") != description("/acheteurs/999-inexistant")


def test_description_contient_le_nom_de_l_organisme(client):
    import re

    from src.utils.data import DF_ACHETEURS

    org_id = DF_ACHETEURS.item(0, "acheteur_id")
    nom = DF_ACHETEURS.item(0, "acheteur_nom")
    body = client.get(f"/acheteurs/{org_id}").get_data(as_text=True)
    description = re.findall(r'<meta name="description" content="(.*?)"', body)[0]
    assert nom in description


def test_canonical_servi_dans_le_html(client):
    """Plus de href posé par JavaScript : la balise est servie remplie."""
    body = client.get("/tableau").get_data(as_text=True)
    assert 'rel="canonical" href="http://localhost/tableau"' in body


def test_canonical_ignore_la_query_string(client):
    body = client.get("/tableau?acheteur=X").get_data(as_text=True)
    assert 'href="http://localhost/tableau"' in body


def test_canonical_ignore_x_forwarded_host_non_fiable(client):
    """nginx ne transmet jamais X-Forwarded-Host (deploy/nginx-colibre.conf) :
    ProxyFix ne doit donc pas s'y fier, sans quoi n'importe quel client pourrait
    faire servir un canonical pointant vers un domaine tiers de son choix."""
    body = client.get("/tableau", headers={"X-Forwarded-Host": "evil.tld"}).get_data(
        as_text=True
    )
    assert "evil.tld" not in body
    assert 'rel="canonical" href="http://localhost/tableau"' in body


def test_canonical_reflete_x_forwarded_proto_https(client):
    """`ProxyFix(x_proto=1)` (src/app.py) : sans lui, Flask croit servir en
    http derrière nginx et le canonical sortirait en http:// en production,
    c'est-à-dire vers une URL qui redirige (voir deploy/nginx-yunohost-prod.conf).
    """
    body = client.get("/tableau", headers={"X-Forwarded-Proto": "https"}).get_data(
        as_text=True
    )
    assert 'rel="canonical" href="https://localhost/tableau"' in body


def test_jsonld_organisme_servi_dans_le_html(client):
    import json
    import re

    body = client.get("/acheteurs/123").get_data(as_text=True)
    blocs = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', body, re.S
    )
    donnees = [json.loads(b) for b in blocs if b.strip()]
    assert any(d.get("name") == "ACHETEUR 1" for d in donnees)


def test_jsonld_minimal_sans_appel_reseau(monkeypatch):
    """La version servie ne doit jamais appeler l'Annuaire des entreprises."""
    from src.utils import data, seo

    def interdit(*_a, **_k):
        raise AssertionError("appel réseau interdit dans le rendu serveur")

    monkeypatch.setattr(data, "get_annuaire_data", interdit)
    resultat = seo.make_org_jsonld_minimal("123", "acheteur", "ACHETEUR 1")
    assert resultat["name"] == "ACHETEUR 1"
    assert "address" not in resultat


def test_jsonld_minimal_pas_pour_une_page_non_organisme(client):
    """Aucun bloc JSON-LD, quel que soit son contenu, sur une page non-organisme.

    Un simple `"GovernmentOrganization" not in body` resterait vrai si le code
    posait par erreur un bloc JSON-LD de type "Organization" (titulaire) sur
    cette page : on vérifie l'absence de la balise <script ld+json> elle-même.
    `/tableau` a un seul segment de chemin (échoue tôt sur la vérification de
    longueur) ; `/projet/presentation` a deux segments comme une fiche
    acheteur/titulaire mais un premier segment différent, ce qui exerce
    réellement le filtre sur le nom du segment plutôt que sur sa seule
    longueur.
    """
    for chemin in ("/tableau", "/projet/presentation"):
        body = client.get(chemin).get_data(as_text=True)
        assert "application/ld+json" not in body, chemin


def test_jsonld_minimal_echappe_uniquement_les_chevrons(monkeypatch):
    """Un nom d'organisme avec guillemets et chevrons reste du JSON analysable.

    Échapper en HTML (markupsafe.escape) transformerait les guillemets en
    `&quot;` et casserait le parsing JSON-LD ; seule la séquence `<` doit être
    neutralisée, pour empêcher une fermeture prématurée de la balise
    <script>.
    """
    import json

    import polars as pl

    from src.app import _org_jsonld_tag
    from src.utils import data

    nom_piege = 'Mairie "Test" <script>alert(1)</script>'
    faux_df = pl.DataFrame({"acheteur_id": ["999"], "acheteur_nom": [nom_piege]})
    monkeypatch.setattr(data, "DF_ACHETEURS", faux_df)

    tag = _org_jsonld_tag("/acheteurs/999")

    assert "&quot;" not in tag
    assert "</script>alert" not in tag

    payload = tag.removeprefix('<script type="application/ld+json">').removesuffix(
        "</script>"
    )
    parsed = json.loads(payload)
    assert parsed["name"] == nom_piege
