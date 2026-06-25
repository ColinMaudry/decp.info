import pytest

from src.subscriptions import client, plans


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    plans._trial_cache.clear()


def test_resolve_handle(monkeypatch):
    assert plans.resolve_handle("simple") == "plan_simple"
    assert plans.resolve_handle("inconnu") is None


def test_trial_days_parses_and_caches(monkeypatch):
    calls = []

    def fake_get_plan(handle):
        calls.append(handle)
        return {"trial_interval": "2d"}

    monkeypatch.setattr(client, "get_plan", fake_get_plan)
    assert plans.trial_days("simple") == 2
    assert plans.trial_days("simple") == 2  # depuis le cache
    assert calls == ["plan_simple"]  # un seul appel API


def test_trial_days_none_on_error(monkeypatch):
    def fake_get_plan(handle):
        raise client.FrisbiiError(500, "boom")

    monkeypatch.setattr(client, "get_plan", fake_get_plan)
    assert plans.trial_days("simple") is None


def test_trial_days_none_when_no_trial(monkeypatch):
    monkeypatch.setattr(client, "get_plan", lambda h: {"trial_interval": None})
    assert plans.trial_days("simple") is None
