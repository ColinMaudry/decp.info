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


def test_content_for_current_user_passes_only_vote_state(monkeypatch):
    """L'essai vote comme un abonnement : le contenu votable ne dépend que du
    solde et du rechargement, sans câblage spécifique à l'essai."""
    from src.roadmap import view as roadmap_view

    class _FakeUser:
        id = 1
        is_authenticated = True

    monkeypatch.setattr(roadmap_view, "current_user_has_subscription", lambda: True)
    monkeypatch.setattr(roadmap_view, "current_user", _FakeUser())
    monkeypatch.setattr(roadmap_view.subs_db, "credit_pending", lambda _: 3)
    monkeypatch.setattr(roadmap_view.subs_db, "next_recharge_at", lambda _: None)

    captured = {}

    def _fake_roadmap_content(**kwargs):
        captured.update(kwargs)
        return "content"

    monkeypatch.setattr(
        roadmap_view.roadmap_ui, "roadmap_content", _fake_roadmap_content
    )

    roadmap_view.content_for_current_user()
    assert captured == {"editable": True, "balance": 3, "next_recharge": None}
