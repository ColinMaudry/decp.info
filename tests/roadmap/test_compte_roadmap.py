def test_module_imports_and_registers():
    from src.pages.compte import roadmap as compte_roadmap

    assert callable(compte_roadmap.layout)
    assert callable(compte_roadmap.cast_vote)
