from src.pages import _compte_shell as shell


def test_visible_sections_hides_gated_without_subscription():
    keys = {s["key"] for s in shell.visible_sections(has_subscription=False)}
    assert "admin" in keys
    assert "abonnement" in keys
    assert "archives" not in keys


def test_visible_sections_shows_all_with_subscription():
    keys = {s["key"] for s in shell.visible_sections(has_subscription=True)}
    assert "archives" in keys


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
