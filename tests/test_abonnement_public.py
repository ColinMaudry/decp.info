import pytest


@pytest.fixture(autouse=True)
def _plan_env(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")


def test_plan_cards_show_single_trial_mention_above_cards_no_per_card_badge():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page
    from src.subscriptions.db import TRIAL_DAYS

    result = page._plan_cards()
    # La mention d'essai est un élément à part, placé avant la rangée des
    # cartes de formule.
    mention, row = result.children
    mention_text = str(mention)
    assert f"{TRIAL_DAYS} jours d'essai gratuit" in mention_text
    assert "sans carte bancaire" in mention_text

    row_text = str(row)
    # Les deux cartes de formule sont toujours là...
    assert "Abonnement" in row_text
    assert "Abonnement de soutien" in row_text
    assert "S'abonner" not in row_text
    # ... mais elles ne portent plus de badge d'essai individuel.
    assert "essai gratuit" not in row_text


def test_subscribe_button_visitor_goes_to_inscription():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page._subscribe_button(False, False, False))
    assert "Je crée mon compte" in text
    assert "href='/inscription'" in text


def test_subscribe_button_authenticated_no_sub_goes_to_mes_infos_even_during_trial():
    # Page de conversion : un·e utilisateur·rice authentifié·e sans abonnement
    # (y compris pendant son essai gratuit, qui n'est plus une propriété
    # d'abonnement) doit toujours voir « Je m'abonne » vers mes-infos, jamais
    # « Gérer mon abonnement ».
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page._subscribe_button(True, False, False))
    assert "Je m'abonne" in text
    assert "href='/compte/abonnement/mes-infos'" in text
    assert "Gérer mon abonnement" not in text


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
    assert "Je crée mon compte" in text
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


def test_subscription_terms_limited_to_commercial_clauses():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page.subscription_terms)
    assert "Droit de rétractation" in text
    assert "se renouvelle automatiquement" in text
    assert "L441-10" in text
    # les conditions d'utilisation ont migré vers les mentions légales
    assert "Chatwoot" not in text
    assert "Adresse e-mail (identification du compte)" not in text
    assert "/a-propos/mentions-legales#conditions-utilisation" in text


def test_subscription_terms_mentions_trial_days_from_config():
    """Revue #132 : la durée d'essai citée dans les CGV légalement revues doit
    suivre TRIAL_DAYS, sinon un changement de durée fait mentir le texte
    contractuel sans que la suite le remarque."""
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page
    from src.subscriptions.db import TRIAL_DAYS

    text = str(page.subscription_terms)
    assert f"essai gratuit de {TRIAL_DAYS} jours" in text


def test_subscription_terms_trial_no_longer_auto_converts_to_paid():
    # Depuis le passage de l'essai hors Frisbii (aucun prélèvement possible
    # pendant l'essai), les conditions ne doivent plus décrire de
    # transformation automatique de l'essai en abonnement payant : c'est la
    # souscription explicite qui démarre l'abonnement, jamais la fin de
    # l'essai.
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    text = str(page.subscription_terms)
    # La nouvelle formulation est bien présente...
    assert "L'abonnement payant démarre à la souscription à un abonnement" in text
    # ... et les anciennes formulations décrivant une conversion automatique
    # de l'essai en abonnement payant ont disparu.
    assert "l'abonnement payant démarre et la première facture est émise" not in text
    assert "ne démarre qu'à l'issue de la période d'essai" not in text


def test_plan_card_ttc_price_for_current_real_prices():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import abonnement as page

    simple = str(
        page._plan_card(
            {
                "label": "Abonnement",
                "prix_ht": 20,
                "description": "desc",
            }
        )
    )
    assert "24 € TTC" in simple

    soutien = str(
        page._plan_card(
            {
                "label": "Abonnement de soutien",
                "prix_ht": 50,
                "description": "desc",
            }
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
            }
        )
    )
    assert "28.8 € TTC" in text
    assert "28.799999999999997" not in text
