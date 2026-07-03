from unittest.mock import patch

from src.admin import guard


def _fake_user(email: str, authenticated: bool = True):
    user = type("U", (), {})()
    user.is_authenticated = authenticated
    user.email = email
    return user


def test_is_admin_true_for_matching_email(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@ex.fr")
    with patch("src.admin.guard.current_user", _fake_user("admin@ex.fr")):
        assert guard.is_admin() is True


def test_is_admin_true_case_insensitive(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "Admin@Ex.fr")
    with patch("src.admin.guard.current_user", _fake_user("admin@ex.fr")):
        assert guard.is_admin() is True


def test_is_admin_false_for_different_email(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@ex.fr")
    with patch("src.admin.guard.current_user", _fake_user("someone@ex.fr")):
        assert guard.is_admin() is False


def test_is_admin_false_for_anonymous(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@ex.fr")
    with patch(
        "src.admin.guard.current_user", _fake_user("admin@ex.fr", authenticated=False)
    ):
        assert guard.is_admin() is False


def test_is_admin_false_when_admin_email_unset(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    with patch("src.admin.guard.current_user", _fake_user("admin@ex.fr")):
        assert guard.is_admin() is False
