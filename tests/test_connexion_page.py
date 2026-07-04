def test_connexion_cta_points_to_abonnement():
    from src.app import app  # noqa: F401  # initializes Dash app
    from src.pages import connexion

    text = str(connexion.layout())
    assert "/a-propos/abonnement" in text
    assert "Voir les abonnements" in text
