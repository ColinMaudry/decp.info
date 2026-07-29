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
