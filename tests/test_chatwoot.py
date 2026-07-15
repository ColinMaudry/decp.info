from src.utils.chatwoot import build_widget_script


def test_no_token_returns_empty_string():
    assert build_widget_script(None) == ""


def test_empty_token_returns_empty_string():
    assert build_widget_script("") == ""


def test_token_produces_script_with_token_and_managed_base_url():
    script = build_widget_script("PVejdJRyKtSZdEkJtDJQ3xCd")
    assert "<script>" in script
    assert "websiteToken: 'PVejdJRyKtSZdEkJtDJQ3xCd'" in script
    assert "baseUrl: BASE_URL" in script
    assert 'BASE_URL="https://app.chatwoot.com"' in script
