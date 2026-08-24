"""Page publique /projet/roadmap : lecture seule, sauf pour les abonné·es."""

import pytest

# L'ID du bouton de vote est un motif ; sa repr contient cette chaîne. On ne peut
# pas chercher "roadmap-vote" seul, qui est aussi un préfixe de la liste
# "roadmap-vote-list", toujours présente.
VOTE_BUTTON = "'type': 'roadmap-vote'"


class _FakeUser:
    id = 1
    is_authenticated = True


@pytest.fixture
def fake_issues(monkeypatch):
    from src.roadmap import ui as roadmap_ui

    monkeypatch.setattr(
        roadmap_ui.github,
        "fetch_roadmap_issues",
        lambda: {
            "en_cours": [],
            "au_vote": [{"number": 1, "title": "Feature publique", "html_url": "u1"}],
        },
    )
    monkeypatch.setattr(roadmap_ui.roadmap_db, "vote_counts", lambda: {1: 4})


def _layout(monkeypatch, *, subscriber: bool, balance: int = 0):
    from src.roadmap import view as roadmap_view

    monkeypatch.setattr(
        roadmap_view, "current_user_has_subscription", lambda: subscriber
    )
    if subscriber:
        monkeypatch.setattr(roadmap_view, "current_user", _FakeUser())
        monkeypatch.setattr(roadmap_view.subs_db, "credit_pending", lambda _: balance)
        monkeypatch.setattr(roadmap_view.subs_db, "next_recharge_at", lambda _: None)
        monkeypatch.setattr(roadmap_view.subs_db, "get_current", lambda _: None)

    from src.pages.projet import roadmap

    return str(roadmap.layout())


def test_visiteuse_non_abonnee_voit_la_lecture_seule(monkeypatch, fake_issues):
    s = _layout(monkeypatch, subscriber=False)
    assert "Feature publique" in s
    assert VOTE_BUTTON not in s
    assert "Votes restants" not in s


def test_visiteuse_non_abonnee_voit_l_appel_a_l_abonnement(monkeypatch, fake_issues):
    s = _layout(monkeypatch, subscriber=False)
    assert "Abonnez-vous" in s
    assert "/projet/abonnement" in s


def test_abonnee_peut_voter_depuis_la_page_publique(monkeypatch, fake_issues):
    s = _layout(monkeypatch, subscriber=True, balance=3)
    assert "Feature publique" in s
    assert VOTE_BUTTON in s
    assert "Votes restants" in s
    assert "Abonnez-vous" not in s  # pas d'appel à l'abonnement pour une abonnée


def test_abonnee_sans_solde_voit_les_boutons_desactives(monkeypatch, fake_issues):
    s = _layout(monkeypatch, subscriber=True, balance=0)
    assert VOTE_BUTTON in s
    assert "disabled=True" in s
