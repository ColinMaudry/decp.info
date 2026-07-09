import src.utils.tracking as tracking


def test_track_mcp_tool_sends_action_and_dimension(monkeypatch):
    captured = {}

    def fake_post(url, params):
        captured["url"] = url
        captured["params"] = params

        class _R:
            def raise_for_status(self):
                pass

        return _R()

    monkeypatch.setattr(tracking, "DEVELOPMENT", False)
    monkeypatch.setattr(tracking, "post", fake_post)
    monkeypatch.setenv("MATOMO_DOMAIN", "matomo.example")
    monkeypatch.setenv("MATOMO_ID_SITE", "1")

    tracking.track_mcp_tool("rechercher_marches", query="informatique")

    assert captured["params"]["action_name"] == "MCP / rechercher_marches"
    assert captured["params"]["dimension1"] == "rechercher_marches"
    assert captured["params"]["search"] == "informatique"


def test_track_mcp_tool_noop_in_development(monkeypatch):
    called = False

    def fake_post(url, params):
        nonlocal called
        called = True

    monkeypatch.setattr(tracking, "DEVELOPMENT", True)
    monkeypatch.setattr(tracking, "post", fake_post)
    monkeypatch.setenv("MATOMO_DOMAIN", "matomo.example")

    tracking.track_mcp_tool("stats_acheteur")

    assert called is False
