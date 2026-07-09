from src.mcp import tools


def test_all_four_tools_are_callable():
    for name in (
        "rechercher_organisations",
        "stats_acheteur",
        "stats_titulaire",
        "rechercher_marches",
    ):
        assert callable(getattr(tools, name))


def test_rechercher_organisations_returns_list():
    result = tools.rechercher_organisations("ACHETEUR", "acheteur")
    assert isinstance(result, list)
    assert any(r["id"] == "123" for r in result)


def test_rechercher_marches_returns_meta():
    result = tools.rechercher_marches(acheteur_id="123")
    assert result["meta"]["total"] >= 1


def test_stats_acheteur_returns_stats():
    result = tools.stats_acheteur("123")
    assert result["nb_marches"] >= 1
    assert result["identite"]["id"] == "123"


def test_stats_titulaire_returns_stats():
    result = tools.stats_titulaire("345")
    assert result["nb_marches"] >= 1
