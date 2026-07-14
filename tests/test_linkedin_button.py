def test_linkedin_button_default_has_no_next():
    # Import app first to initialize Dash
    from src.app import app  # noqa: F401
    from src.pages.connexion import linkedin_button

    html_str = str(linkedin_button())
    assert "href='/auth/linkedin'" in html_str
    assert "next=" not in html_str


def test_linkedin_button_with_next_appends_query():
    # Import app first to initialize Dash
    from src.app import app  # noqa: F401
    from src.pages.connexion import linkedin_button

    html_str = str(linkedin_button("/compte/abonnement/mes-infos"))
    assert "/auth/linkedin?next=/compte/abonnement/mes-infos" in html_str


def test_inscription_linkedin_targets_mes_infos():
    # Import app first to initialize Dash
    from src.app import app  # noqa: F401
    from src.pages import inscription

    assert "/auth/linkedin?next=/compte/abonnement/mes-infos" in str(
        inscription.layout()
    )


def test_inscription_linkedin_targets_abonnement_when_tous_abonnes(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    # Import app first to initialize Dash
    from src.app import app  # noqa: F401
    from src.pages import inscription

    assert "/auth/linkedin?next=/compte/abonnement'" in str(inscription.layout())
