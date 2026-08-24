from datetime import datetime, timedelta, timezone

import pytest

from src.mcp.oauth import consent


@pytest.fixture
def users_db_path(monkeypatch, tmp_path):
    from src.auth.db import reset_conn_for_tests

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    reset_conn_for_tests()
    yield db_path
    reset_conn_for_tests()


def test_subscription_ok_tous_abonnes(monkeypatch):
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", True)
    assert consent.subscription_ok(999) is True


def test_subscription_ok_delegates(monkeypatch):
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    monkeypatch.setattr("src.mcp.oauth.consent.has_access", lambda uid: uid == 7)
    assert consent.subscription_ok(7) is True
    assert consent.subscription_ok(8) is False


def test_subscription_ok_true_during_trial_without_subscriptions_row(
    users_db_path, monkeypatch
):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("trial-oauth@ex.fr", "hash")
    sub_db.start_trial_if_new(uid)

    # Ancrage positif : essai actif, aucune ligne subscriptions.
    assert sub_db.trial_active(uid) is True
    assert sub_db.get_current(uid) is None

    assert consent.subscription_ok(uid) is True


def test_subscription_ok_false_after_trial_expires_without_subscriptions_row(
    users_db_path, monkeypatch
):
    from src.auth import db as auth_db
    from src.auth.db import get_conn
    from src.subscriptions import db as sub_db

    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("trial-oauth-expire@ex.fr", "hash")
    sub_db.start_trial_if_new(uid)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    get_conn().execute(
        "UPDATE subscriber_state SET trial_ends_at = ? WHERE user_id = ?",
        (past, uid),
    )

    # Ancrage positif : essai expiré, toujours aucune ligne subscriptions.
    assert sub_db.trial_active(uid) is False
    assert sub_db.get_current(uid) is None

    assert consent.subscription_ok(uid) is False


def test_render_consent_shows_redirect_host():
    html = consent.render_consent(
        "Claude", "https://claude.ai/api/mcp/auth_callback", "mcp"
    )
    assert "claude.ai" in html
    assert "Claude" in html
    assert 'name="confirm"' in html


def test_render_subscription_required_links_abonnement():
    html = consent.render_subscription_required()
    assert "/compte/abonnement" in html


def test_render_consent_escapes_client_name():
    html = consent.render_consent(
        "<script>alert(1)</script>",
        "https://claude.ai/api/mcp/auth_callback",
        "mcp",
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_consent_includes_csrf_token():
    html = consent.render_consent(
        "Claude",
        "https://claude.ai/api/mcp/auth_callback",
        "mcp",
        csrf_token="tok-abc-123",
    )
    assert 'name="csrf_token"' in html
    assert "tok-abc-123" in html
