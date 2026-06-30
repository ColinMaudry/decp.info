from dash.testing.composite import DashComposite


def _rgb_tuple(css_color: str) -> tuple[int, int, int]:
    """Parse 'rgb(r, g, b)' ou 'rgba(r, g, b, a)' en (r, g, b)."""
    inner = css_color[css_color.index("(") + 1 : css_color.index(")")]
    parts = [p.strip() for p in inner.split(",")]
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def test_btn_primary_is_terracotta(dash_duo: DashComposite):
    """Garde de non-régression : le bouton primaire de l'accueil conserve son
    dégradé terracotta et son texte blanc après l'override de la charte."""
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_element("a.btn.btn-primary, button.btn.btn-primary", timeout=10)
    btn = dash_duo.find_element("a.btn.btn-primary, button.btn.btn-primary")

    # Le dégradé terracotta est posé via background-image ; le texte est blanc.
    bg_image = btn.value_of_css_property("background-image")
    color = btn.value_of_css_property("color")

    assert "gradient" in bg_image  # dégradé terracotta appliqué
    assert _rgb_tuple(color) == (255, 255, 255)  # texte blanc
