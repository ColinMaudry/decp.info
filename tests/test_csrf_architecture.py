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


def test_fill_csrf_inputs_allows_initial_call():
    """_fill_csrf_inputs ne doit pas avoir prevent_initial_call=True.

    Avec prevent_initial_call=True, le callback n'est pas déclenché lors de la chaîne
    initiale (_pages_location → _generate_csrf_token → csrf-token → _fill_csrf_inputs),
    laissant le champ csrf_token vide → erreur 400 au premier chargement de /connexion.
    """
    import src.app  # noqa: F401 — enregistre les callbacks

    found = False
    for cb_info in dash._callback.GLOBAL_CALLBACK_MAP.values():
        inputs = getattr(cb_info, "inputs", None) or cb_info.get("inputs", [])
        for inp in inputs:
            if hasattr(inp, "component_id"):
                inp_id, inp_prop = inp.component_id, inp.component_property
            else:
                inp_id, inp_prop = inp.get("id"), inp.get("property")

            if inp_id == "csrf-token" and inp_prop == "data":
                pic = getattr(cb_info, "prevent_initial_call", None)
                if pic is None:
                    pic = cb_info.get("prevent_initial_call", False)
                assert not pic, (
                    "_fill_csrf_inputs a prevent_initial_call=True — le token CSRF "
                    "ne sera pas injecté lors du premier chargement de /connexion."
                )
                found = True

    assert found, (
        "Callback avec Input('csrf-token', 'data') introuvable dans le registre Dash. "
        "Vérifier que _fill_csrf_inputs est toujours enregistré dans src/app.py."
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
