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


def test_client_instructions_include_oauth_apps():
    from src.app import app  # noqa: F401
    from src.pages.compte.mcp import client_instructions

    comp = client_instructions("https://colibre.fr/_mcp", "<VOTRE_JETON>")
    titles = _collect_titles(comp)
    assert any("Claude.ai" in t for t in titles)
    assert any("ChatGPT" in t for t in titles)


def _collect_titles(component):
    # Parcourt récursivement les AccordionItem pour collecter leurs `title`.
    found = []

    def walk(node):
        title = getattr(node, "title", None)
        if isinstance(title, str):
            found.append(title)
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            for c in children:
                walk(c)
        elif children is not None:
            walk(children)

    walk(component)
    return found
