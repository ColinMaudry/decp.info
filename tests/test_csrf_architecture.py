"""
Vérifie que les callbacks CSRF n'utilisent pas d'IDs string page-spécifiques
comme outputs, ce qui provoquerait des erreurs Dash "id non trouvé dans le layout".
"""

import dash


def _find_component_id(component, target_id):
    """Parcourt récursivement le layout Dash à la recherche d'un composant par id."""
    if hasattr(component, "id") and component.id == target_id:
        return True
    children = getattr(component, "children", None)
    if isinstance(children, list):
        return any(_find_component_id(c, target_id) for c in children)
    if children is not None:
        return _find_component_id(children, target_id)
    return False


def test_csrf_token_store_in_main_layout():
    """dcc.Store(id='csrf-token') doit être dans le layout principal (toujours présent)."""
    from src.app import app

    assert _find_component_id(app.layout, "csrf-token"), (
        "dcc.Store(id='csrf-token') manquant dans le layout principal. "
        "Sans lui, les callbacks CSRF référencent des composants absents du layout initial."
    )


def test_no_page_specific_csrf_callback_outputs():
    """Aucun callback CSRF ne doit cibler un ID string page-spécifique en Output."""
    old_ids = {
        "csrf-login.value",
        "csrf-signup.value",
        "csrf-forgot.value",
        "csrf-change.value",
        "csrf-logout.value",
        "csrf-reset.value",
        "csrf-navbar-logout.value",
    }

    found = [k for k in dash._callback.GLOBAL_CALLBACK_MAP if k in old_ids]

    assert not found, (
        "Callbacks CSRF avec IDs string trouvés — provoquent des erreurs Dash au démarrage.\n"
        + "\n".join(found)
    )
