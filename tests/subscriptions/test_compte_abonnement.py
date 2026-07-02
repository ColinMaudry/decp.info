def test_plan_cards_present_when_no_subscription(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    from src.pages.compte import abonnement as compte_abonnement

    cards = compte_abonnement._plan_cards(trial_for=lambda key: 2)
    text = str(cards)
    assert "Abonnement" in text
    assert "Abonnement de soutien" in text
    assert "2 jours d'essai gratuit" in text


def test_plan_cards_no_trial_when_trial_used(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._plan_cards(trial_used=True, trial_for=lambda key: 2))
    assert "Sans période d'essai" in text
    assert "2 jours d'essai gratuit" not in text


def test_active_view_shows_cancel(monkeypatch):
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    view = compte_abonnement._active_view(row)
    assert "Me désabonner" in str(view)


def test_active_view_trial_banner(monkeypatch):
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "trial",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    assert "Essai gratuit" in str(compte_abonnement._active_view(row))


def test_subscribe_buttons_disabled_when_tous_abonnes(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._plan_cards(trial_for=lambda key: 2))
    assert "btn-secondary disabled" in text
    assert "btn-primary" not in text


def test_subscribe_buttons_active_when_flag_off(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._plan_cards(trial_for=lambda key: 2))
    assert "btn-primary" in text


def test_banner_present_when_tous_abonnes(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._tous_abonnes_banner())
    assert "accessibles à tous et toutes" in text


def test_banner_absent_when_flag_off(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    from src.pages.compte import abonnement as compte_abonnement

    assert compte_abonnement._tous_abonnes_banner() is None


def test_show_active_view_true_for_live_statuses(monkeypatch):
    from src.pages.compte import abonnement as compte_abonnement

    for status in ("pending", "trial", "active", "cancelled", "expired"):
        assert compte_abonnement._show_active_view({"status": status}) is True


def test_show_active_view_false_for_failed_or_none(monkeypatch):
    from src.pages.compte import abonnement as compte_abonnement

    assert compte_abonnement._show_active_view({"status": "failed"}) is False
    assert compte_abonnement._show_active_view(None) is False
