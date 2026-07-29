"""Garde-fou sur le préchauffage du registre de ressources Dash.

Sans le préchauffage à la fin de src/app.py, `registered_paths` reste vide
jusqu'à la première requête, remplie par le before_request `_setup_server` qui
pose son drapeau avant de travailler et sans verrou. Sur un worker gthread neuf,
une requête concurrente lit alors un registre partiel et /_dash-component-suites
répond 500 (« "plotly" is not a registered library »).
"""

from src.app import app


def test_registre_de_ressources_prechauffe_des_l_import():
    assert "plotly" in app.registered_paths
    assert "dash" in app.registered_paths


def test_plotly_js_servi_sur_un_worker_froid():
    """L'URL que le renderer code en dur (sans empreinte) doit répondre 200."""
    resp = app.server.test_client().get(
        "/_dash-component-suites/plotly/package_data/plotly.min.js"
    )
    assert resp.status_code == 200
