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


def test_inscription_linkedin_targets_compte_abonnement():
    # Import app first to initialize Dash
    from src.app import app  # noqa: F401
    from src.pages import inscription

    assert "/auth/linkedin?next=/compte/abonnement'" in str(inscription.layout())


def test_inscription_linkedin_targets_compte_abonnement_even_when_tous_abonnes(
    monkeypatch,
):
    # Il n'y a plus de branche TOUS_ABONNES pour linkedin_next : la page
    # mes-infos est désormais la seule à ouvrir l'essai, quel que soit
    # TOUS_ABONNES.
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    # Import app first to initialize Dash
    from src.app import app  # noqa: F401
    from src.pages import inscription

    assert "/auth/linkedin?next=/compte/abonnement'" in str(inscription.layout())


def test_inscription_announces_trial_start_on_email_validation_no_card_required():
    # Import app first to initialize Dash
    from src.app import app  # noqa: F401
    from src.pages import inscription
    from src.subscriptions.db import TRIAL_DAYS

    text = str(inscription.layout())
    assert "Créer le compte" in text
    assert f"essai gratuit de {TRIAL_DAYS} jours" in text
    assert "démarre dès la validation de votre adresse email" in text
    assert "Aucune carte bancaire n'est demandée" in text
