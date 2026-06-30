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


def test_robots_declares_sitemap(client):
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Sitemap: https://colibre.fr/sitemap.xml" in body


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
