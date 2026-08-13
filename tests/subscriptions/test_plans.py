import pytest

from src.subscriptions import plans


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")


def test_resolve_handle(monkeypatch):
    assert plans.resolve_handle("simple") == "plan_simple"
    assert plans.resolve_handle("inconnu") is None


def test_resolve_handle_unset_env_returns_none(monkeypatch):
    """Fix 3 : une variable d'env vide doit donner None, pas une chaîne vide."""
    monkeypatch.delenv("FRISBII_PLAN_SIMPLE", raising=False)
    assert plans.resolve_handle("simple") is None


def test_plan_meta_handle_none_when_unset(monkeypatch):
    """Fix 3 : plan_meta doit exposer handle=None quand l'env var est absente."""
    monkeypatch.delenv("FRISBII_PLAN_SIMPLE", raising=False)
    meta = plans.plan_meta("simple")
    assert meta is not None
    assert meta["handle"] is None
