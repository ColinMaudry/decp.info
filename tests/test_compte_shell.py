from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.pages import _compte_shell as shell


def _fake_user(authenticated: bool, uid: int = 1):
    user = type("U", (), {})()
    user.is_authenticated = authenticated
    user.id = uid
    return user


@pytest.fixture
def users_db_path(monkeypatch, tmp_path):
    from src.auth.db import reset_conn_for_tests

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    reset_conn_for_tests()
    yield db_path
    reset_conn_for_tests()


def test_visible_sections_hides_gated_without_subscription():
    keys = {s["key"] for s in shell.visible_sections(has_subscription=False)}
    assert "admin" in keys
    assert "abonnement" in keys
    assert "archives" not in keys


def test_visible_sections_shows_all_with_subscription():
    keys = {s["key"] for s in shell.visible_sections(has_subscription=True)}
    assert "roadmap" in keys


def test_guard_redirect_anonymous_goes_to_login():
    href = shell.guard_redirect(
        is_authenticated=False,
        has_subscription=False,
        require_subscription=False,
        path="/compte/admin",
    )
    assert href == "/connexion?next=/compte/admin"


def test_guard_redirect_unsubscribed_on_gated_goes_to_abonnement():
    href = shell.guard_redirect(
        is_authenticated=True,
        has_subscription=False,
        require_subscription=True,
        path="/compte/archives",
    )
    assert href == "/compte/abonnement"


def test_guard_redirect_allowed_returns_none():
    href = shell.guard_redirect(
        is_authenticated=True,
        has_subscription=False,
        require_subscription=False,
        path="/compte/admin",
    )
    assert href is None


def test_has_subscription_true_for_authenticated_when_tous_abonnes(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    with patch("src.pages._compte_shell.current_user", _fake_user(True)):
        assert shell.current_user_has_subscription() is True


def test_has_subscription_false_for_anonymous_even_with_tous_abonnes(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    with patch("src.pages._compte_shell.current_user", _fake_user(False)):
        assert shell.current_user_has_subscription() is False


def test_has_subscription_uses_db_when_flag_off(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    with (
        patch("src.pages._compte_shell.current_user", _fake_user(True)),
        patch("src.subscriptions.db.has_access", return_value=False) as mocked,
    ):
        assert shell.current_user_has_subscription() is False
        mocked.assert_called_once_with(1)


def test_has_subscription_true_during_trial_without_subscriptions_row(
    users_db_path, monkeypatch
):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("essai@ex.fr", "hash")
    sub_db.start_trial_if_new(uid)

    # Ancrage positif : l'essai est bien actif, et aucune ligne subscriptions
    # n'existe pour cet utilisateur.
    assert sub_db.trial_active(uid) is True
    assert sub_db.get_current(uid) is None

    with patch("src.pages._compte_shell.current_user", _fake_user(True, uid)):
        assert shell.current_user_has_subscription() is True


def test_has_subscription_false_after_trial_expires_without_subscriptions_row(
    users_db_path, monkeypatch
):
    from src.auth import db as auth_db
    from src.auth.db import get_conn
    from src.subscriptions import db as sub_db

    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("essai-expire@ex.fr", "hash")
    sub_db.start_trial_if_new(uid)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    get_conn().execute(
        "UPDATE subscriber_state SET trial_ends_at = ? WHERE user_id = ?",
        (past, uid),
    )

    # Ancrage positif : l'essai a bien basculé côté "expiré", et il n'y a
    # toujours aucune ligne subscriptions.
    assert sub_db.trial_active(uid) is False
    assert sub_db.get_current(uid) is None

    with patch("src.pages._compte_shell.current_user", _fake_user(True, uid)):
        assert shell.current_user_has_subscription() is False


def test_barre_laterale_compte_reste_visible_au_defilement():
    from dash import html

    from src.app import app
    from tests.helpers import walk_components

    # current_user (Flask-Login) exige un contexte de requête.
    with app.server.test_request_context("/compte"):
        noeuds = list(walk_components(shell.account_shell("abonnement", html.Div())))

    assert any(
        "shell-nav-sticky" in (getattr(n, "className", "") or "") for n in noeuds
    )
