def test_reabo_button_links_to_abonnement_page():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._reabo_button())
    assert "Abonnez-vous" in text
    assert "/a-propos/abonnement" in text


def test_free_access_view_message():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._free_access_view())
    assert "temporairement accès à toutes les fonctionnalités" in text
    assert "Pensez à copier les liens vers vos vues" in text


def test_no_sub_view_uses_free_access_when_tous_abonnes():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._no_sub_view(True, None))
    assert "temporairement accès" in text
    assert "Abonnez-vous" not in text


def test_no_sub_view_uses_reabo_when_flag_off():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._no_sub_view(False, None))
    assert "Abonnez-vous" in text
    assert "temporairement accès" not in text


def test_no_sub_view_shows_expired_alert_when_flag_off():
    from src.pages.compte import abonnement as compte_abonnement

    row = {"status": "expired", "current_period_end": None}
    text = str(compte_abonnement._no_sub_view(False, row))
    assert "expiré" in text
    assert "Abonnez-vous" in text


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


def test_active_view_trial_banner_shows_date_and_time():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "trial",
        "current_period_end": "2026-07-29T13:57:43.177+00:00",
    }
    text = str(compte_abonnement._active_view(row))
    # essai de 2 jours : l'heure de fin compte autant que le jour
    assert "29 juillet 2026 à 15h57" in text


def test_active_view_trial_banner_without_end_date():
    from src.pages.compte import abonnement as compte_abonnement

    row = {"plan": "simple", "status": "trial", "current_period_end": None}
    text = str(compte_abonnement._active_view(row))
    assert "Essai gratuit" in text
    assert "None" not in text


def test_active_view_cancelled_shows_date_and_time():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "cancelled",
        "current_period_end": "2026-08-08T08:09:21.244+00:00",
    }
    assert "8 août 2026 à 10h09" in str(compte_abonnement._active_view(row))


def test_active_view_active_shows_date_and_time():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "active",
        "current_period_end": "2026-08-08T08:09:21.244+00:00",
    }
    assert "Prochaine facturation : 8 août 2026 à 10h09" in str(
        compte_abonnement._active_view(row)
    )


def test_active_view_never_prints_none_without_end_date():
    from src.pages.compte import abonnement as compte_abonnement

    for status in ("trial", "cancelled", "active"):
        row = {"plan": "simple", "status": status, "current_period_end": None}
        assert "None" not in str(compte_abonnement._active_view(row))


def test_resiliation_modal_shows_date_and_time():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._resiliation_modal("2026-08-08T08:09:21.244+00:00"))
    assert "8 août 2026 à 10h09" in text


def test_banner_present_when_tous_abonnes(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._tous_abonnes_banner())
    assert "temporairement accessibles gratuitement" in text


def test_banner_absent_when_flag_off(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    from src.pages.compte import abonnement as compte_abonnement

    assert compte_abonnement._tous_abonnes_banner() is None


def test_show_active_view_true_for_live_statuses(monkeypatch):
    from src.pages.compte import abonnement as compte_abonnement

    for status in ("pending", "trial", "active", "cancelled"):
        assert compte_abonnement._show_active_view({"status": status}) is True


def test_show_active_view_false_for_failed_expired_or_none(monkeypatch):
    from src.pages.compte import abonnement as compte_abonnement

    assert compte_abonnement._show_active_view({"status": "failed"}) is False
    assert compte_abonnement._show_active_view({"status": "expired"}) is False
    assert compte_abonnement._show_active_view(None) is False


def test_active_view_shows_change_payment_method_for_active():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    text = str(compte_abonnement._active_view(row))
    assert "Changer de méthode de paiement" in text
    assert "/subscriptions/change-payment-method" in text


def test_active_view_shows_change_payment_method_for_trial():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "trial",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    assert "Changer de méthode de paiement" in str(compte_abonnement._active_view(row))


def test_active_view_hides_change_payment_method_for_cancelled():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "cancelled",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    assert "Changer de méthode de paiement" not in str(
        compte_abonnement._active_view(row)
    )


def test_active_view_hides_change_payment_method_for_pending():
    from src.pages.compte import abonnement as compte_abonnement

    row = {"plan": "simple", "status": "pending", "current_period_end": None}
    text = str(compte_abonnement._active_view(row))
    assert "Changer de méthode de paiement" not in text
    assert "Ajouter une méthode de paiement" in text


def test_feedback_carte_succes():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._feedback({"carte": "succes"}))
    assert "Méthode de paiement mise à jour." in text


def test_feedback_carte_annule():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._feedback({"carte": "annule"}))
    assert "Modification annulée." in text


def test_price_text_rounds_ttc():
    from src.pages.compte import abonnement as compte_abonnement

    assert compte_abonnement._price_text({"prix_ht": 20}) == "20 € HT / mois (24 € TTC)"
    assert compte_abonnement._price_text({"prix_ht": 50}) == "50 € HT / mois (60 € TTC)"
    assert compte_abonnement._price_text({"label": "x"}) is None


def test_active_view_shows_price():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    assert "24 € TTC" in str(compte_abonnement._active_view(row))


def test_active_view_shows_configure_button_for_active():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    text = str(compte_abonnement._active_view(row))
    assert "Configurer mon abonnement" in text
    assert "href='/compte/abonnement/mes-infos'" in text


def test_active_view_shows_configure_button_for_pending():
    from src.pages.compte import abonnement as compte_abonnement

    row = {"plan": "simple", "status": "pending", "current_period_end": None}
    assert "Configurer mon abonnement" in str(compte_abonnement._active_view(row))


def test_active_view_hides_configure_button_for_cancelled():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "cancelled",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    assert "Configurer mon abonnement" not in str(compte_abonnement._active_view(row))


def test_feedback_maj_succes():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._feedback({"maj": "succes"}))
    assert "Votre abonnement a été mis à jour." in text
