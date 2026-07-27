def test_conditions_utilisation_section_presente():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import mentions_legales as page

    text = str(page.layout())
    assert "Conditions d'utilisation" in text
    # ancre cible du lien de consentement dans le tunnel de paiement
    assert "conditions-utilisation" in text
    assert "cu-donnees-personnelles" in text


def test_conditions_utilisation_couvrent_le_site_pas_l_abonnement():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import mentions_legales as page

    text = str(page.layout())
    # contenu généraliste, dont le bloc RGPD rapatrié depuis la page abonnement
    assert "Chatwoot" in text
    assert "Loi applicable" in text
    # les clauses commerciales restent dans les conditions d'abonnement
    assert "L441-10" not in text
    assert "rétractation" not in text


def test_mentions_legales_conservent_leurs_sections():
    from src.app import app  # noqa: F401
    from src.pages.a_propos import mentions_legales as page

    text = str(page.layout())
    for ancre in ("publication", "audience", "attributions", "liste_marches"):
        assert ancre in text
