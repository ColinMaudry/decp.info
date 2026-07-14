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


def test_subscribe_button_tous_abonnes_visitor_free_signup():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page._subscribe_button(False, False, True))
    assert "Je m'abonne gratuitement" in text
    assert "href='/inscription'" in text
    assert "disabled" not in text


def test_subscribe_button_tous_abonnes_authenticated_goes_to_compte():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page._subscribe_button(True, False, True))
    assert "href='/compte/abonnement'" in text
    assert "disabled" not in text


def test_cgu_terms_trimmed_of_features_section():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page.subscription_terms)
    assert "Fonctionnalités incluses" not in text
    assert "Résiliation" in text
    assert "Tarifs" in text


def test_plan_card_ttc_price_for_current_real_prices():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    simple = str(
        page._plan_card(
            {
                "label": "Abonnement",
                "prix_ht": 20,
                "description": "desc",
            },
            None,
        )
    )
    assert "24 € TTC" in simple

    soutien = str(
        page._plan_card(
            {
                "label": "Abonnement de soutien",
                "prix_ht": 50,
                "description": "desc",
            },
            None,
        )
    )
    assert "60 € TTC" in soutien


def test_plan_card_ttc_price_avoids_float_artifacts():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(
        page._plan_card(
            {
                "label": "Abonnement non-rond",
                "prix_ht": 24,
                "description": "desc",
            },
            None,
        )
    )
    assert "28.8 € TTC" in text
    assert "28.799999999999997" not in text
