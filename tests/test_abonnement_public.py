import pytest


@pytest.fixture(autouse=True)
def _plan_env(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")


def test_plan_cards_informative_no_button():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page._plan_cards(trial_for=lambda key: 2))
    assert "Abonnement" in text
    assert "Abonnement de soutien" in text
    assert "2 jours d'essai gratuit" in text
    assert "S'abonner" not in text


def test_subscribe_button_visitor_goes_to_inscription():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page._subscribe_button(False, False, False))
    assert "Je m'abonne" in text
    assert "href='/inscription'" in text


def test_subscribe_button_authenticated_no_sub_goes_to_mes_infos():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page._subscribe_button(True, False, False))
    assert "href='/compte/abonnement/mes-infos'" in text


def test_subscribe_button_active_sub_manages():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page._subscribe_button(True, True, False))
    assert "Gérer mon abonnement" in text
    assert "href='/compte/abonnement'" in text


def test_subscribe_button_disabled_when_tous_abonnes():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page._subscribe_button(False, False, True))
    assert "disabled" in text


def test_cgu_terms_trimmed_of_features_section():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page.subscription_terms)
    assert "Fonctionnalités incluses" not in text
    assert "Résiliation" in text
    assert "Tarifs" in text
