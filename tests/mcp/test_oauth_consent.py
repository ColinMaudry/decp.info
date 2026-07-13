from src.mcp.oauth import consent


def test_subscription_ok_tous_abonnes(monkeypatch):
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", True)
    assert consent.subscription_ok(999) is True


def test_subscription_ok_delegates(monkeypatch):
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    monkeypatch.setattr(
        "src.mcp.oauth.consent.has_active_subscription", lambda uid: uid == 7
    )
    assert consent.subscription_ok(7) is True
    assert consent.subscription_ok(8) is False


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
