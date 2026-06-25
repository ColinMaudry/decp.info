def test_plan_cards_present_when_no_subscription(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    from src.pages import compte_abonnement

    cards = compte_abonnement._plan_cards(trial_for=lambda key: 2)
    text = str(cards)
    assert "Abonnement simple" in text
    assert "Abonnement de soutien" in text
    assert "2 jours d'essai gratuit" in text


def test_plan_cards_no_trial_when_trial_used(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    from src.pages import compte_abonnement

    text = str(compte_abonnement._plan_cards(trial_used=True, trial_for=lambda key: 2))
    assert "Sans période d'essai" in text
    assert "2 jours d'essai gratuit" not in text


def test_active_view_shows_cancel(monkeypatch):
    from src.pages import compte_abonnement

    row = {
        "plan": "simple",
        "status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    view = compte_abonnement._active_view(row)
    assert "Résilier" in str(view)


def test_active_view_trial_banner(monkeypatch):
    from src.pages import compte_abonnement

    row = {
        "plan": "simple",
        "status": "trial",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    assert "Essai gratuit" in str(compte_abonnement._active_view(row))
