import src.utils.search as search_mod
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
