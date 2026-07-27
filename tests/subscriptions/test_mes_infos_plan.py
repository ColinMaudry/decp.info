import pytest


@pytest.fixture(autouse=True)
def _plan_env(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")


def test_layout_redirects_to_abonnement_when_tous_abonnes(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    from src.pages.compte import abonnement_mes_infos as m

    text = str(m.layout())
    # redirection du flag vers /compte/abonnement (href exact), pas le guard de
    # connexion ni un renvoi vers la page carte bancaire mes-infos
    assert "href='/compte/abonnement'" in text
    assert "Mes informations de facturation" not in text
    assert "connexion" not in text


def test_selectable_cards_render_both_plans():
    from src.pages.compte import abonnement_mes_infos as m

    text = str(m._selectable_cards(trial_for=lambda key: 2))
    assert "plan-card-simple" in text
    assert "plan-card-soutien" in text
    assert "plan-selectable" in text
    assert "Abonnement de soutien" in text


def test_selection_state_simple():
    from src.pages.compte import abonnement_mes_infos as m

    value, cls_simple, cls_soutien = m._selection_state("simple")
    assert value == "simple"
    assert "selected" in cls_simple
    assert "selected" not in cls_soutien


def test_selection_state_soutien():
    from src.pages.compte import abonnement_mes_infos as m

    value, cls_simple, cls_soutien = m._selection_state("soutien")
    assert value == "soutien"
    assert "selected" in cls_soutien
    assert "selected" not in cls_simple


def test_submit_disabled_without_plan():
    from src.pages.compte import abonnement_mes_infos as m

    assert m._toggle_submit(["ok"], ["ok"], ["ok"], "") is True
    assert m._toggle_submit(["ok"], ["ok"], ["ok"], "simple") is False
    assert m._toggle_submit([], ["ok"], ["ok"], "simple") is True
    # les conditions d'utilisation et d'abonnement sont acceptées séparément
    assert m._toggle_submit(["ok"], [], ["ok"], "simple") is True
    assert m._toggle_submit(["ok"], ["ok"], [], "simple") is True


def test_recap_lines_cover_fields_required_in_checkout():
    from datetime import date

    from src.pages.compte import abonnement_mes_infos as m

    lines = dict(m._recap_lines("simple", 2, date(2026, 7, 27)))
    assert "SAS Colmo" in lines["Vendeur"]
    assert "98939335000016" in lines["Vendeur"]
    assert "Abonnement" in lines["Prestation"]
    assert lines["Période d'essai gratuite"].startswith("du 27/07/2026 au 29/07/2026")
    # l'abonnement payant démarre à la fin de l'essai, pas à la saisie de carte
    assert lines["Début de l'abonnement payant"] == "29/07/2026"
    assert "1 mois" in lines["Durée"]
    assert "20 € HT" in lines["Prix"]
    assert "24 € TTC" in lines["Prix"]
    assert "EUR" in lines["Prix"]


def test_recap_lines_without_trial_start_today():
    from datetime import date

    from src.pages.compte import abonnement_mes_infos as m

    lines = dict(m._recap_lines("soutien", None, date(2026, 7, 27)))
    assert "Période d'essai gratuite" not in lines
    assert lines["Début de l'abonnement payant"] == "27/07/2026"
    assert "50 € HT" in lines["Prix"]


def test_recap_placeholder_without_selected_plan():
    from src.pages.compte import abonnement_mes_infos as m

    text = str(m._recap(None, None))
    assert "Choisissez une formule" in text
    assert "Vendeur" not in text


def test_selection_state_leaves_the_invite_label_alone():
    from src.pages.compte import abonnement_mes_infos as m

    # « Choisissez votre formule : » doit rester visible une fois une carte
    # cliquée : _select_plan ne pilote plus la className de inf-plan-invite,
    # donc _selection_state ne renvoie plus de classe pour ce composant.
    assert len(m._selection_state("simple")) == 3
    assert "d-none" not in m._selection_state("simple")


def test_initial_plan_defaults_to_simple_in_subscribe_mode():
    from src.pages.compte import abonnement_mes_infos as m

    # sans pré-sélection, le bouton reste inactif et le récapitulatif vide
    # tant qu'aucune carte n'est cliquée
    assert m._initial_plan("subscribe", None) == "simple"
    assert m._initial_plan("subscribe", {"plan": "soutien"}) == "simple"


def test_initial_plan_keeps_current_plan_in_configure_mode():
    from src.pages.compte import abonnement_mes_infos as m

    assert m._initial_plan("configure", {"plan": "soutien"}) == "soutien"
    assert m._initial_plan("configure", {"plan": "simple"}) == "simple"


def test_default_plan_is_the_20_euros_one():
    from src.pages.compte import abonnement_mes_infos as m
    from src.subscriptions import plans

    assert plans.PLANS[m._DEFAULT_PLAN]["prix_ht"] == 20


def test_selectable_cards_mark_default_plan_selected():
    from src.pages.compte import abonnement_mes_infos as m

    text = str(m._selectable_cards(trial_for=lambda key: 2, selected="simple"))
    assert "plan-selectable selected" in text


def test_mode_for_derives_from_status():
    from src.pages.compte import abonnement_mes_infos as m

    for status in ("active", "trial", "pending"):
        assert m._mode_for({"status": status}) == "configure"
    assert m._mode_for({"status": "cancelled"}) == "subscribe"
    assert m._mode_for({"status": "expired"}) == "subscribe"
    assert m._mode_for(None) == "subscribe"


def test_submit_button_subscribe_mode():
    from src.pages.compte import abonnement_mes_infos as m

    text = str(m._submit_button("subscribe"))
    assert "Ajouter une carte de paiement" in text
    assert "disabled" in text


def test_submit_button_configure_mode():
    from src.pages.compte import abonnement_mes_infos as m

    btn = m._submit_button("configure")
    text = str(btn)
    assert "Mettre à jour mon abonnement" in text
    assert btn.disabled is False


def test_selectable_cards_preselects_current_plan():
    from src.pages.compte import abonnement_mes_infos as m

    text = str(m._selectable_cards(trial_for=lambda key: None, selected="soutien"))
    # la card soutien est marquée sélectionnée, pas la card simple
    assert "plan-selectable selected" in text


def test_change_hint_shown_when_plan_differs():
    from src.pages.compte import abonnement_mes_infos as m

    cls, txt = m._change_hint(
        "soutien",
        {"current_plan": "simple", "status": "active", "echeance": "1er janvier"},
    )
    assert cls != "d-none"
    assert "prochaine échéance : 1er janvier" in txt


def test_change_hint_hidden_when_same_plan():
    from src.pages.compte import abonnement_mes_infos as m

    cls, txt = m._change_hint(
        "simple",
        {"current_plan": "simple", "status": "active", "echeance": "1er janvier"},
    )
    assert cls == "d-none"
    assert txt == ""


def test_change_hint_hidden_for_pending():
    from src.pages.compte import abonnement_mes_infos as m

    cls, _ = m._change_hint(
        "soutien",
        {"current_plan": "simple", "status": "pending", "echeance": None},
    )
    assert cls == "d-none"


def test_change_hint_hidden_in_subscribe_mode():
    from src.pages.compte import abonnement_mes_infos as m

    cls, _ = m._change_hint("soutien", {})
    assert cls == "d-none"


def test_consent_checklists_ids_always_present_in_configure_mode():
    # Régression : le callback _toggle_submit référence inf-cb-retractation,
    # inf-cb-cgu et inf-cb-cgv en Input inconditionnellement, donc ces
    # composants doivent exister dans le layout même en mode "configure"
    # (sinon Dash lève "A nonexistent object was used in an Input").
    from src.pages.compte import abonnement_mes_infos as m

    div = m._consent_checklists(hidden=True)
    text = str(div)
    assert "inf-cb-retractation" in text
    assert "inf-cb-cgu" in text
    assert "inf-cb-cgv" in text
    assert "d-none" in div.className


def test_consent_checklists_pre_accepted_when_hidden():
    from src.pages.compte import abonnement_mes_infos as m

    div = m._consent_checklists(hidden=True)
    retractation, cgu, cgv = div.children
    assert retractation.value == ["ok"]
    assert cgu.value == ["ok"]
    assert cgv.value == ["ok"]


def test_consent_checklists_visible_and_empty_in_subscribe_mode():
    from src.pages.compte import abonnement_mes_infos as m

    div = m._consent_checklists(hidden=False)
    retractation, cgu, cgv = div.children
    assert retractation.value == []
    assert cgu.value == []
    assert cgv.value == []
    assert div.className is None
