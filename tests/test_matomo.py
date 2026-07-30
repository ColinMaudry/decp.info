"""Fragment de suivi Matomo partagé entre les pages Dash et SEO SSR (#128)."""


def test_desactive_par_defaut(monkeypatch):
    """La suite tourne avec MATOMO_TRACKING_ENABLED=false (pyproject.toml)."""
    from src.utils.matomo import build_tracker_script

    monkeypatch.delenv("MATOMO_TRACKING_ENABLED", raising=False)
    assert build_tracker_script() == ""


def test_desactive_explicitement(monkeypatch):
    from src.utils.matomo import build_tracker_script

    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "false")
    assert build_tracker_script() == ""


def test_active_rend_le_script_trackpageview(monkeypatch):
    from src.utils.matomo import build_tracker_script

    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    script = build_tracker_script()
    assert "trackPageView" in script
    assert "<script" in script and "</script>" in script
