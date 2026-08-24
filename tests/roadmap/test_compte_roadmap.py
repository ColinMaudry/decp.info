def test_module_imports_and_registers():
    from src.pages.compte import roadmap as compte_roadmap

    assert callable(compte_roadmap.layout)


def test_cast_vote_est_partage_par_les_deux_pages():
    """Le callback vit dans src.roadmap.view, pas dans un module de page.

    Dans une page, Dash le ré-enregistrerait pendant la découverte use_pages
    (« Duplicate callback outputs »).
    """
    from src.pages.compte import roadmap as compte_roadmap
    from src.pages.projet import roadmap as projet_roadmap
    from src.roadmap import view as roadmap_view

    assert callable(roadmap_view.cast_vote)
    assert not hasattr(compte_roadmap, "cast_vote")
    assert projet_roadmap.roadmap_view is compte_roadmap.roadmap_view
