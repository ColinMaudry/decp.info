from dash import dcc, html

from src.roadmap import ui


def test_balance_text_singular_plural():
    assert ui.balance_text(1) == "Il te reste 1 vote."
    assert ui.balance_text(3) == "Il te reste 3 votes."


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
    assert "Voter" in str(ui.vote_items(au_vote, {1: 0}, editable=True))
    assert "Voter" not in str(ui.vote_items(au_vote, {1: 0}, editable=False))


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
    assert "Il te reste 2 votes." in s
