"""Redirections depuis les anciennes URLs de l'arbre départemental."""

import pytest


@pytest.fixture(scope="module")
def client():
    from src.app import app

    return app.server.test_client()


def test_ancienne_liste_marches_301_vers_la_nouvelle(client):
    resp = client.get("/departements/06/acheteur/123")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/acheteurs/123/marches")


def test_ancienne_liste_marches_titulaire(client):
    resp = client.get("/departements/35/titulaire/345")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/titulaires/345/marches")


def test_ancienne_page_departement_301(client):
    resp = client.get("/departements/75")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/departements/75/acheteurs")


def test_type_inconnu_dans_l_ancienne_url_404(client):
    assert client.get("/departements/06/autre/123").status_code == 404


def test_plus_aucune_page_dash_sous_departements():
    from dash import page_registry

    chemins = {p["path"] for p in page_registry.values()}
    gabarits = {p.get("path_template") for p in page_registry.values()}
    assert not any(c.startswith("/departements") for c in chemins)
    assert not any(g and g.startswith("/departements") for g in gabarits)
