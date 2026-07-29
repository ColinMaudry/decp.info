"""Statut HTTP 404 sur les chemins qui ne correspondent à aucune page (#125).

Avant le correctif, le catch-all `<path:path>` de Dash servait la coquille de
l'index en 200 pour n'importe quel chemin, dont les `/db` héritées de l'ancien
decp.info.
"""

import pytest


@pytest.fixture(scope="module")
def client():
    from src.app import app

    return app.server.test_client()


@pytest.mark.parametrize(
    "path",
    [
        "/db",
        "/db/decp.csv",
        "/acheteur",  # singulier : la page réelle est /acheteurs/<id>
        "/nimportequoi",
        "/a-propos/inexistant",
        "/404",  # la page 404 elle-même ne doit pas répondre 200
    ],
)
def test_chemins_inconnus_renvoient_404(client, path):
    resp = client.get(path)
    assert resp.status_code == 404
    assert "Page introuvable" in resp.get_data(as_text=True)


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/tableau",
        "/observatoire",
        "/a-propos/contact",
        "/connexion",
    ],
)
def test_pages_statiques_inchangees(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/marches/abc",
        "/acheteurs/123",
        "/titulaires/345",
        "/departements/44",
        "/departements/44/acheteur/123",
    ],
)
def test_pages_a_gabarit_inchangees(client, path):
    """Les gabarits `/marches/<uid>` & co. restent servis par Dash."""
    assert client.get(path).status_code == 200


def test_routes_hors_catchall_inchangees(client):
    """robots.txt, sitemap et assets ont leurs propres règles Flask."""
    assert client.get("/robots.txt").status_code == 200
    assert client.get("/sitemap.xml").status_code == 200
    # 404 servi par Dash lui-même, pas par le garde
    assert client.get("/assets/inexistant.css").status_code == 404


def test_page_dash_404_enregistree_sous_le_bon_nom_de_module():
    """Dash repère la page par son nom de module (dash.py:2654), pas son path.

    Sans ce nom exact, le routeur SPA retombe sur son H1 anglais par défaut.
    """
    import dash

    modules = {m.split(".")[-1] for m in dash.page_registry}
    assert "not_found_404" in modules
