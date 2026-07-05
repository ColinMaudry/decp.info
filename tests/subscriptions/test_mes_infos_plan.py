import pytest


@pytest.fixture(autouse=True)
def _plan_env(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")


def test_selectable_cards_render_both_plans():
    from src.pages.compte import abonnement_mes_infos as m

    text = str(m._selectable_cards(trial_for=lambda key: 2))
    assert "plan-card-simple" in text
    assert "plan-card-soutien" in text
    assert "plan-selectable" in text
    assert "Abonnement de soutien" in text


def test_selection_state_simple():
    from src.pages.compte import abonnement_mes_infos as m

    value, cls_simple, cls_soutien, cls_invite = m._selection_state("simple")
    assert value == "simple"
    assert "selected" in cls_simple
    assert "selected" not in cls_soutien
    assert cls_invite == "d-none"


def test_selection_state_soutien():
    from src.pages.compte import abonnement_mes_infos as m

    value, cls_simple, cls_soutien, _ = m._selection_state("soutien")
    assert value == "soutien"
    assert "selected" in cls_soutien
    assert "selected" not in cls_simple


def test_submit_disabled_without_plan():
    from src.pages.compte import abonnement_mes_infos as m

    assert m._toggle_submit(["ok"], ["ok"], "") is True
    assert m._toggle_submit(["ok"], ["ok"], "simple") is False
    assert m._toggle_submit([], ["ok"], "simple") is True


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
