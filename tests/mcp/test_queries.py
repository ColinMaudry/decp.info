import pytest

import src.utils.search as search_mod
from src.mcp.queries import search_organisations
from src.utils.data import DF_ACHETEURS
from src.utils.search import search_org


def test_search_org_track_false_skips_track_search(monkeypatch):
    calls = []
    monkeypatch.setattr(search_mod, "track_search", lambda q, c: calls.append((q, c)))

    search_org(DF_ACHETEURS, "ACHETEUR", "acheteur", track=False)

    assert calls == []


def test_search_org_track_true_calls_track_search(monkeypatch):
    calls = []
    monkeypatch.setattr(search_mod, "track_search", lambda q, c: calls.append((q, c)))

    search_org(DF_ACHETEURS, "ACHETEUR", "acheteur", track=True)

    assert calls == [("ACHETEUR", "home_page_search")]


def test_search_organisations_finds_known_acheteur():
    result = search_organisations("ACHETEUR", "acheteur")
    assert any(r["id"] == "123" for r in result)
    first = next(r for r in result if r["id"] == "123")
    assert set(first.keys()) == {"id", "nom", "departement"}
    # Vérifier que le nom a été extrait en texte plain (HTML strippé)
    assert first["nom"] == "ACHETEUR 1"
    assert "<" not in first["nom"]  # Défense : aucun markup HTML ne s'échappe


def test_search_organisations_invalid_type_raises():
    with pytest.raises(ValueError):
        search_organisations("x", "autre")


def test_search_organisations_respects_limite():
    result = search_organisations("ACHETEUR", "acheteur", limite=1)
    assert len(result) <= 1
