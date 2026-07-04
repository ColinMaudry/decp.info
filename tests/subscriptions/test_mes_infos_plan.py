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
