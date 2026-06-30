def test_public_layout_renders_read_only(monkeypatch):
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

    from src.pages.a_propos import roadmap

    layout = roadmap.layout()
    s = str(layout)
    assert "Feature publique" in s
    assert "Voter" not in s  # lecture seule : aucun bouton
