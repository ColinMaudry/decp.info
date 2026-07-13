"""Régression : le datasource server-side de la grille entité (_get_rows) doit
répondre sans erreur de callback Dash.

Bug migration AG Grid (#41) : _get_rows mélangeait une sortie MATCH
(getRowsResponse de la grille pattern-matching) avec des sorties fixes
(acheteur-total / -total-unique). Dash l'interdit (« MATCH wildcards must be on
the same keys for all Outputs ») — l'erreur est levée par le dev-renderer en
mode debug (celui de `run.py`), pas par le renderer de production. Le callback
échoue alors au dispatch et la grille ne reçoit aucune ligne.

Ce test tourne donc en `debug=True` (dev-renderer) pour exercer cette
validation, sinon le bug passe inaperçu. Le correctif : une seule sortie MATCH,
les stores totaux alimentés via dash.set_props.
"""

import src.app  # noqa: F401  # instancie l'app → register_page()
from src.db import query_marches


def _an_acheteur_id():
    return query_marches("TRUE", (), columns=["acheteur_id"])["acheteur_id"][0]


def test_entity_grid_datasource_returns_rows_in_debug(dash_duo):
    from src.app import app

    ach = _an_acheteur_id()

    # debug=True → dev-renderer, qui valide la cohérence MATCH des Outputs.
    dash_duo.start_server(
        app, debug=True, use_reloader=False, dev_tools_hot_reload=False
    )
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=6)
    dash_duo.wait_for_page(dash_duo.server_url + f"/acheteurs/{ach}")

    # La grille charge des lignes → _get_rows a répondu (pas d'erreur de dispatch).
    dash_duo.wait_for_element(
        "#acheteur-grid-container .ag-center-cols-container .ag-row", timeout=15
    )
    # nb_rows alimenté via les stores totaux mis à jour par set_props côté serveur.
    dash_duo.wait_for_contains_text("#acheteur_nb_rows", "marchés", timeout=8)
    assert "0 marchés" not in dash_duo.find_element("#acheteur_nb_rows").text

    # Aucune erreur « Mismatched MATCH wildcards » dans la console du dev-renderer.
    match_errors = [
        entry
        for entry in (dash_duo.get_logs() or [])
        if "MATCH" in str(entry.get("message", ""))
    ]
    assert not match_errors, f"Erreur dev-renderer MATCH : {match_errors}"
