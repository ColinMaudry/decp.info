"""Régression : pour un visiteur non abonné, la barre des vues sauvegardées
reste visible, mais « Sauvegarder la vue » et « Mes vues » sont grisés et
désactivés (le gating serveur de save_view reste par ailleurs en place).
"""

import src.app  # noqa: F401  # instancie l'app → register_page()


def test_controls_disabled_for_anonymous_visitor(dash_duo):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=6)
    dash_duo.wait_for_page(dash_duo.server_url + "/tableau")

    # La barre est visible pour tous.
    bar = dash_duo.wait_for_element("#saved-views-bar", timeout=10)
    assert bar.value_of_css_property("display") != "none"

    # « Sauvegarder la vue » est désactivé (donc grisé) pour un anonyme.
    save_btn = dash_duo.find_element("#btn-save-view")
    assert save_btn.get_attribute("disabled") is not None

    # « Mes vues » (le bouton toggle du DropdownMenu) est désactivé aussi.
    menu_toggle = dash_duo.find_element("#saved-views-menu .dropdown-toggle")
    disabled_attr = menu_toggle.get_attribute("disabled")
    has_disabled_class = "disabled" in (menu_toggle.get_attribute("class") or "")
    assert disabled_attr is not None or has_disabled_class
