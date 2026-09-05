from datetime import datetime, timezone


class _FakeUser:
    id = 1
    is_authenticated = True


def _layout(
    monkeypatch,
    *,
    row=None,
    trial_active=False,
    trial_ends_at=None,
    tous_abonnes=False,
    **query,
):
    """Rend layout() en cablant db.get_current/trial_active/trial_ends_at et en
    court-circuitant account_guard (déjà testé par ailleurs dans
    tests/test_compte_shell.py) pour isoler le dispatch d'état de layout()."""
    from src.pages.compte import abonnement as compte_abonnement
    from src.subscriptions import db as sub_db

    monkeypatch.setattr(compte_abonnement, "account_guard", lambda *a, **k: None)
    monkeypatch.setattr(compte_abonnement, "current_user", _FakeUser())
    monkeypatch.setattr("src.utils.TOUS_ABONNES", tous_abonnes)
    monkeypatch.setattr(sub_db, "get_current", lambda uid: row)
    monkeypatch.setattr(sub_db, "trial_active", lambda uid: trial_active)
    monkeypatch.setattr(sub_db, "trial_ends_at", lambda uid: trial_ends_at)
    return str(compte_abonnement.layout(**query))


def test_layout_tous_abonnes_shows_free_access_view(monkeypatch):
    text = _layout(monkeypatch, row=None, tous_abonnes=True)
    assert "temporairement accès à toutes les fonctionnalités" in text
    assert "Essai gratuit" not in text
    assert "Abonnez-vous" not in text


def test_layout_trial_active_shows_trial_view(monkeypatch):
    end = datetime(2026, 9, 1, tzinfo=timezone.utc)
    text = _layout(monkeypatch, row=None, trial_active=True, trial_ends_at=end)
    assert "Essai gratuit jusqu'au" in text
    assert "temporairement accès" not in text
    assert "Votre essai gratuit est terminé" not in text
    assert "Abonnez-vous" not in text


def test_layout_trial_ended_shows_trial_ended_view(monkeypatch):
    past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    text = _layout(monkeypatch, row=None, trial_active=False, trial_ends_at=past)
    assert "Votre essai gratuit est terminé" in text
    assert "Essai gratuit jusqu'au" not in text
    assert "temporairement accès" not in text
    assert "Abonnez-vous" not in text


def test_layout_never_had_trial_shows_reabo_view(monkeypatch):
    text = _layout(monkeypatch, row=None, trial_active=False, trial_ends_at=None)
    assert "Abonnez-vous" in text
    assert "temporairement accès" not in text
    assert "Votre essai gratuit est terminé" not in text
    assert "Essai gratuit" not in text


def test_layout_pending_with_active_trial_shows_trial_end_and_reabo(
    monkeypatch,
):
    """Revue #132 : un checkout abandonné pendant l'essai ne doit pas faire
    disparaître la date de fin d'essai ni le moyen de repartir en souscription.

    Depuis 720685a, ce moyen est le bouton de souscription normal
    (`_reabo_button`) et non plus un bouton « Reprendre le paiement » dédié.
    """
    end = datetime(2026, 9, 1, tzinfo=timezone.utc)
    row = {"status": "pending", "plan": "simple", "current_period_end": None}
    text = _layout(monkeypatch, row=row, trial_active=True, trial_ends_at=end)
    assert "Essai gratuit jusqu'au" in text
    assert "Abonnez-vous" in text


def test_layout_pending_without_active_trial_keeps_pending_view(monkeypatch):
    """Comportement inchangé : ligne pending sans essai actif (jamais eu ou
    déjà terminé) reste sur la vue "abonnement en cours" (_active_view)."""
    row = {"status": "pending", "plan": "simple", "current_period_end": None}
    text = _layout(monkeypatch, row=row, trial_active=False, trial_ends_at=None)
    assert "souscription à un abonnement n'a pas abouti" in text
    assert "Essai gratuit" not in text


def test_resume_payment_renvoie_vers_le_parcours_normal_pas_add_payment(monkeypatch):
    """Un checkout abandonné ne laisse plus aucun abonnement chez Frisbii.

    Depuis le passage à `prepare_subscription`, il n'y a donc plus d'abonnement
    auquel attacher un moyen de paiement : `/subscriptions/add-payment`
    échouerait en 404. On repasse par le parcours de souscription normal, qui
    recollecte les informations de facturation avant d'ouvrir une nouvelle
    session — depuis 720685a son point d'entrée est /projet/abonnement.
    """
    row = {"status": "pending", "plan": "simple", "current_period_end": None}
    text = _layout(monkeypatch, row=row, trial_active=False, trial_ends_at=None)
    assert "/projet/abonnement" in text
    assert "/subscriptions/add-payment" not in text


def test_resume_payment_dit_que_la_souscription_n_a_pas_abouti(monkeypatch):
    """Le message doit décrire l'état réel : rien n'existe chez Frisbii.

    Parler d'un « abonnement non finalisé » auquel il manquerait une méthode de
    paiement laissait croire qu'un abonnement attend quelque part, alors qu'une
    ligne `pending` signifie seulement que le paiement n'est pas allé au bout.
    """
    row = {"status": "pending", "plan": "simple", "current_period_end": None}
    text = _layout(monkeypatch, row=row, trial_active=False, trial_ends_at=None)
    assert "souscription à un abonnement n'a pas abouti" in text
    assert "aucune méthode de paiement n'a été enregistrée" not in text


def test_reabo_button_links_to_abonnement_page():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._reabo_button())
    assert "Abonnez-vous" in text
    assert "/projet/abonnement" in text


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


def test_active_view_pending_no_longer_mentions_trial_and_offers_reabo():
    from src.pages.compte import abonnement as compte_abonnement

    row = {"plan": "simple", "status": "pending", "current_period_end": None}
    text = str(compte_abonnement._active_view(row))
    assert "période d'essai" not in text
    assert "Abonnez-vous" in text


def test_trial_view_shows_end_date_and_time_and_features():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._trial_view("2026-07-29T13:57:43.177+00:00"))
    # essai de 2 jours : l'heure de fin compte autant que le jour
    assert "29 juillet 2026 à 15h57" in text
    assert "Votre essai débloque" in text
    assert "sauvegardez et partagez des" in text


def test_trial_view_without_end_date():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._trial_view(None))
    assert "Essai gratuit en cours" in text
    assert "None" not in text


def test_trial_view_offers_early_subscription_with_immediate_charge_notice():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._trial_view(None))
    assert "Je m'abonne dès maintenant" in text
    assert "/compte/abonnement/mes-infos" in text
    assert "Votre essai débloque" in text


def test_trial_ended_view_shows_start_subscription_button_and_link():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._trial_ended_view())
    assert "Commencer mon abonnement" in text
    assert "/compte/abonnement/mes-infos" in text


def test_trial_ended_view_shows_no_amount():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._trial_ended_view())
    assert "Commencer mon abonnement" in text
    assert "€" not in text


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
    assert "Prochaine facturation et prélèvement : 8 août 2026 à 10h09" in str(
        compte_abonnement._active_view(row)
    )


def test_active_view_never_prints_none_without_end_date():
    from src.pages.compte import abonnement as compte_abonnement

    for status in ("cancelled", "active"):
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

    for status in ("pending", "active", "cancelled"):
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


def test_active_view_shows_reactivate_button_for_cancelled():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "cancelled",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    text = str(compte_abonnement._active_view(row))
    assert "Je me réabonne" in text
    assert "/subscriptions/reactivate" in text


def test_active_view_hides_reactivate_button_for_active():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    assert "Je me réabonne" not in str(compte_abonnement._active_view(row))


def test_active_view_expired_cancellation_links_to_mes_infos_instead_of_reactivating():
    """Un statut "cancelled" dont la période est déjà dépassée n'a plus
    d'accès en cours (has_active_subscription en jugerait de même) : Frisbii
    refuse l'uncancel sur un abonnement déjà expiré (erreur API "Subscription
    expired"), donc le bouton "Je me réabonne" doit renvoyer vers le parcours
    de souscription normale plutôt que vers /subscriptions/reactivate."""
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "cancelled",
        "current_period_end": "2020-01-01T00:00:00+00:00",
    }
    text = str(compte_abonnement._active_view(row))
    assert "Je me réabonne" in text
    assert "/compte/abonnement/mes-infos" in text
    assert "/subscriptions/reactivate" not in text


def test_feedback_reactivation_ok():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._feedback({"reactivation": "ok"}))
    assert "Votre abonnement a été réactivé." in text


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
    assert "Abonnez-vous" in text


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


def test_active_view_hides_configure_button_for_pending():
    """720685a : sur une ligne pending il n'y a rien à configurer — aucun
    abonnement n'existe chez Frisbii, seule une tentative de paiement a
    échoué. Le seul chemin proposé est de refaire une souscription."""
    from src.pages.compte import abonnement as compte_abonnement

    row = {"plan": "simple", "status": "pending", "current_period_end": None}
    assert "Configurer mon abonnement" not in str(compte_abonnement._active_view(row))


def test_active_view_hides_cancel_for_pending():
    """720685a, même raison : on ne résilie pas un abonnement qui n'existe pas.
    Contraste avec test_active_view_shows_cancel, qui garde le bouton sur une
    ligne active."""
    from src.pages.compte import abonnement as compte_abonnement

    row = {"plan": "simple", "status": "pending", "current_period_end": None}
    assert "Me désabonner" not in str(compte_abonnement._active_view(row))


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
