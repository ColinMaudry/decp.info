import logging

import src.utils.tracking as tracking


def _capturer(monkeypatch):
    """Remplace l'envoi asynchrone par une capture synchrone."""
    envois = []
    monkeypatch.setattr(
        tracking, "_envoyer_async", lambda params: envois.append(params)
    )
    return envois


def test_evenement_abonnement_payant(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    envois = _capturer(monkeypatch)

    tracking.track_subscription_goal("subscription_active", "simple", 20)

    assert len(envois) == 1
    params = envois[0]
    assert params["e_c"] == "Abonnement"
    assert params["e_a"] == "subscription_active"
    assert params["e_n"] == "simple"
    assert params["e_v"] == 20
    assert "token_auth" not in params


def test_evenement_sans_revenu(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    envois = _capturer(monkeypatch)

    tracking.track_subscription_goal("subscription_trial", "soutien")

    assert "e_v" not in envois[0]
    assert envois[0]["e_n"] == "soutien"


def test_muet_sous_tous_abonnes(monkeypatch):
    """Sous TOUS_ABONNES il n'y a pas d'abonnement réel à comptabiliser."""
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    envois = _capturer(monkeypatch)

    tracking.track_subscription_goal("subscription_active", "simple", 20)

    assert envois == []


def test_envoyer_async_appelle_envoyer(monkeypatch):
    recu = {}
    monkeypatch.setattr(tracking, "_envoyer", lambda params: recu.update(params))

    thread = tracking._envoyer_async({"e_a": "subscription_active"})
    thread.join(timeout=5.0)

    assert recu["e_a"] == "subscription_active"


def test_envoyer_async_ne_leve_pas_si_thread_start_echoue(monkeypatch):
    """Une panne au démarrage du thread (ex. RuntimeError sous épuisement de
    ressources) ne doit pas remonter jusqu'à l'appelant : dans
    `update_from_webhook` (src/subscriptions/db.py), une exception non
    rattrapée ici ferait répondre 500 à Frisbii et déclencherait un nouvel
    essai — rejouant la transaction et l'événement.
    """

    class ThreadQuiEchoue:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(tracking.threading, "Thread", ThreadQuiEchoue)

    resultat = tracking._envoyer_async({"e_a": "subscription_active"})

    assert resultat is None


def test_n_exceptionne_pas_si_envoi_echoue(monkeypatch):
    """Une panne Matomo ne doit pas faire répondre 502 au webhook Frisbii.

    On exerce `_envoyer` directement plutôt qu'au travers de
    `track_subscription_goal` : les exceptions levées dans le thread démon de
    `_envoyer_async` ne remontent de toute façon jamais jusqu'à l'appelant
    (garantie du module `threading`, même sans `try/except`), donc appeler
    `track_subscription_goal` ici ne prouverait rien — un `join()` du thread
    ne re-lève pas non plus son exception. La garantie « ne lève jamais » vit
    dans `_envoyer` ; c'est donc elle qu'il faut appeler en synchrone pour
    qu'une régression (suppression du `try/except`) fasse échouer ce test.
    """
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "1")

    def fake_post(url, data, timeout):
        raise RuntimeError("matomo est tombé")

    monkeypatch.setattr(tracking, "post", fake_post)

    tracking._envoyer({"e_a": "subscription_active"})  # ne doit pas lever


def _preparer_echec_envoi(monkeypatch):
    """Configure `_envoyer` pour échouer, et remet `_echec_signale` à `False`.

    Sans cette remise à zéro, l'ordre d'exécution des tests déciderait de ce
    qui passe : `_echec_signale` est un drapeau au niveau module, donc un
    test qui tourne après un autre échec déjà signalé le trouverait à `True`
    et ne verrait jamais son propre warning.
    """
    monkeypatch.setattr(tracking, "_echec_signale", False)
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "1")

    def fake_post(url, data, timeout):
        raise RuntimeError("matomo est tombé")

    monkeypatch.setattr(tracking, "post", fake_post)


def test_premier_echec_emet_un_warning(monkeypatch, caplog):
    _preparer_echec_envoi(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="colibre"):
        tracking._envoyer({"e_a": "subscription_active"})

    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert "Matomo" in caplog.text


def test_second_echec_consecutif_n_emet_pas_de_nouveau_warning(monkeypatch, caplog):
    _preparer_echec_envoi(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="colibre"):
        tracking._envoyer({"e_a": "subscription_active"})  # signale, une fois
        caplog.clear()
        tracking._envoyer({"e_a": "subscription_active"})  # ne re-signale pas

    assert caplog.records == []
