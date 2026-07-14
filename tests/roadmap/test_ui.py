from dash import dcc, html

from src.roadmap import ui


def test_vote_items_sorted_by_count_desc():
    au_vote = [
        {"number": 1, "title": "A", "html_url": "u1"},
        {"number": 2, "title": "B", "html_url": "u2"},
    ]
    counts = {1: 1, 2: 5}
    items = ui.vote_items(au_vote, counts, editable=False)
    # le plus voté (numéro 2) vient en premier
    assert "B" in str(items[0])
    assert "A" in str(items[1])


def test_vote_items_buttons_only_when_editable():
    au_vote = [{"number": 1, "title": "A", "html_url": "u1"}]
    assert "roadmap-vote" in str(ui.vote_items(au_vote, {1: 0}, editable=True))
    assert "roadmap-vote" not in str(ui.vote_items(au_vote, {1: 0}, editable=False))


def test_changelog_markdown_returns_component():
    comp = ui.changelog_markdown()
    assert isinstance(comp, dcc.Markdown)
    assert "##" in comp.children  # le CHANGELOG.md contient des titres markdown


def test_roadmap_content_renders(monkeypatch):
    monkeypatch.setattr(
        ui.github,
        "fetch_roadmap_issues",
        lambda: {
            "en_cours": [{"number": 9, "title": "En cours X", "html_url": "u9"}],
            "au_vote": [{"number": 5, "title": "Au vote Y", "html_url": "u5"}],
        },
    )
    monkeypatch.setattr(ui.roadmap_db, "vote_counts", lambda: {5: 3})
    content = ui.roadmap_content(editable=True, balance=2)
    s = str(content)
    assert isinstance(content, html.Div)
    assert "En cours X" in s
    assert "Au vote Y" in s
    assert "Votes restants" in s
    assert "value='2'" in s


def test_roadmap_content_shows_trial_hint(monkeypatch):
    monkeypatch.setattr(
        ui.github,
        "fetch_roadmap_issues",
        lambda: {"en_cours": [], "au_vote": []},
    )
    monkeypatch.setattr(ui.roadmap_db, "vote_counts", lambda: {})
    content = ui.roadmap_content(
        editable=True,
        balance=0,
        sub_status="trial",
        trial_ends_at="2026-07-20T10:00:00+00:00",
    )
    assert "20/07/2026" in str(content)


def test_roadmap_content_no_trial_hint_when_active(monkeypatch):
    monkeypatch.setattr(
        ui.github,
        "fetch_roadmap_issues",
        lambda: {"en_cours": [], "au_vote": []},
    )
    monkeypatch.setattr(ui.roadmap_db, "vote_counts", lambda: {})
    content = ui.roadmap_content(
        editable=True,
        balance=3,
        sub_status="active",
        trial_ends_at=None,
    )
    assert "période d'essai" not in str(content)
