from datetime import datetime, timezone

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
    trial_ends_at = datetime(2026, 12, 25, 10, 0, tzinfo=timezone.utc)
    content = ui.roadmap_content(
        editable=True,
        balance=0,
        trial_ends_at=trial_ends_at,
    )
    s = str(content)
    assert "25/12/2026" in s
    assert (
        "Le vote est réservé aux abonné·es : il s'ouvrira au début de votre "
        "abonnement." in s
    )


def test_roadmap_content_no_trial_hint_for_paying_subscriber(monkeypatch):
    monkeypatch.setattr(
        ui.github,
        "fetch_roadmap_issues",
        lambda: {
            "en_cours": [],
            "au_vote": [{"number": 5, "title": "Au vote Y", "html_url": "u5"}],
        },
    )
    monkeypatch.setattr(ui.roadmap_db, "vote_counts", lambda: {})
    content = ui.roadmap_content(
        editable=True,
        balance=5,
        trial_ends_at=None,
    )
    s = str(content)
    # Assertion positive : le contenu roadmap est bien rendu (un rendu vide
    # satisferait sinon trivialement l'absence de l'indice ci-dessous).
    assert "Au vote Y" in s
    assert "Votes restants" in s
    assert "il s'ouvrira au début de votre abonnement" not in s


def test_roadmap_content_no_trial_hint_when_not_editable(monkeypatch):
    monkeypatch.setattr(
        ui.github,
        "fetch_roadmap_issues",
        lambda: {
            "en_cours": [],
            "au_vote": [{"number": 1, "title": "Feature publique", "html_url": "u1"}],
        },
    )
    monkeypatch.setattr(ui.roadmap_db, "vote_counts", lambda: {})
    # Un visiteur non abonné (editable=False) ne doit jamais voir l'indice
    # d'essai, même si trial_ends_at était renseigné par erreur.
    content = ui.roadmap_content(
        editable=False,
        trial_ends_at=datetime(2026, 12, 25, 10, 0, tzinfo=timezone.utc),
    )
    s = str(content)
    assert "Feature publique" in s
    assert "Abonnez-vous" in s
    assert "il s'ouvrira au début de votre abonnement" not in s


def test_content_for_current_user_wires_trial_ends_at_only_when_trial_active(
    monkeypatch,
):
    """Prouve le câblage de content_for_current_user, pas seulement le rendu.

    C'est précisément la ligne qui était fausse : trial_ends_at venait de la
    ligne d'abonnement Frisbii (`sub["current_period_end"]`), qui n'existe
    plus pendant l'essai.
    """
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

    # Abonné payant sans essai en cours : trial_ends_at doit valoir None.
    monkeypatch.setattr(roadmap_view.subs_db, "trial_active", lambda _: False)
    monkeypatch.setattr(roadmap_view.subs_db, "trial_ends_at", lambda _: None)
    roadmap_view.content_for_current_user()
    assert captured["trial_ends_at"] is None

    # Utilisateur en essai : trial_ends_at doit être transmis tel quel.
    end = datetime(2026, 9, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(roadmap_view.subs_db, "trial_active", lambda _: True)
    monkeypatch.setattr(roadmap_view.subs_db, "trial_ends_at", lambda _: end)
    roadmap_view.content_for_current_user()
    assert captured["trial_ends_at"] == end
