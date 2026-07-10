def test_section_connecteur_mcp_present():
    from src.pages._compte_shell import SECTIONS

    keys = {s["key"]: s for s in SECTIONS}
    assert "mcp" in keys
    assert keys["mcp"]["label"] == "Connecteur MCP"
    assert keys["mcp"]["href"] == "/compte/mcp"
    assert keys["mcp"]["require_subscription"] is True


def test_page_module_registers_and_builds_client_instructions():
    # importe l'app pour la découverte use_pages en contexte propre
    from src.app import app  # noqa: F401
    from src.pages.compte import mcp as mcp_page

    # helper pur : construit les 4 blocs d'instructions clients
    blocks = mcp_page.client_instructions(
        "https://colibre.fr/_mcp", "colibre_TESTTOKEN"
    )
    text = str(blocks)
    assert "colibre_TESTTOKEN" in text
    assert "https://colibre.fr/_mcp" in text
    for client_name in ("Claude", "Gemini", "Mistral", "ChatGPT"):
        assert client_name in text
    # caveat ChatGPT (OAuth / itération future)
    assert "OAuth" in text
