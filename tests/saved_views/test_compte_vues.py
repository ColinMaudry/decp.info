from src.pages import _compte_shell as shell


def test_vues_section_is_gated_subscription():
    section = next(s for s in shell.SECTIONS if s["key"] == "vues")
    assert section["href"] == "/compte/vues"
    assert section["require_subscription"] is True


def test_vues_hidden_without_subscription():
    keys = {s["key"] for s in shell.visible_sections(has_subscription=False)}
    assert "vues" not in keys


def test_vues_visible_with_subscription():
    keys = {s["key"] for s in shell.visible_sections(has_subscription=True)}
    assert "vues" in keys
