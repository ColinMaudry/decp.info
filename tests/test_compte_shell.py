from unittest.mock import patch

from src.pages import _compte_shell as shell


def _fake_user(authenticated: bool):
    user = type("U", (), {})()
    user.is_authenticated = authenticated
    user.id = 1
    return user


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
        patch(
            "src.subscriptions.db.has_active_subscription", return_value=False
        ) as mocked,
    ):
        assert shell.current_user_has_subscription() is False
        mocked.assert_called_once_with(1)
