"""Navigation latérale des pages /projet/*."""

from tests.helpers import walk_components


def _nav_links(active: str):
    from src.app import app  # noqa: F401
    from src.pages._projet_shell import _nav

    return [n for n in walk_components(_nav(active)) if type(n).__name__ == "NavLink"]


def test_nav_projet_liste_les_sous_sections_de_donnees_quand_elle_est_active():
    hrefs = [n.href for n in _nav_links("donnees")]
    assert hrefs[hrefs.index("/projet/donnees") + 1 :][:4] == [
        "/projet/donnees#donnees-brutes",
        "/projet/donnees#qualite",
        "/projet/donnees#champs",
        "/projet/donnees#sources",
    ]


def test_nav_projet_masque_les_sous_sections_quand_donnees_est_inactive():
    hrefs = [n.href for n in _nav_links("contact")]
    assert not any("#" in href for href in hrefs)
    assert "/projet/donnees" in hrefs


def test_sous_sections_de_donnees_ont_un_libelle_lisible():
    liens = _nav_links("donnees")
    libelles = [n.children for n in liens if n.href.startswith("/projet/donnees#")]
    assert libelles == [
        "Consommer les données brutes",
        "Qualité et exhaustivité",
        "Liste des champs",
        "Sources de données",
    ]


def test_barre_laterale_projet_reste_visible_au_defilement():
    noeuds = list(walk_components(_shell_donnees()))
    assert any(
        "shell-nav-sticky" in (getattr(n, "className", "") or "") for n in noeuds
    )


def _shell_donnees():
    from dash import html

    from src.app import app  # noqa: F401
    from src.pages._projet_shell import projet_shell

    return projet_shell("donnees", html.Div())


def test_menu_burger_mobile_ne_liste_pas_les_sous_sections():
    """Sur mobile la nav est repliée dans un offcanvas : personne ne découvre
    les sous-sections en arrivant sur la page, et cliquer l'une d'elles laisse
    la fermeture du menu ramener la page en haut."""
    offcanvas = next(
        n for n in walk_components(_shell_donnees()) if type(n).__name__ == "Offcanvas"
    )
    hrefs = [
        n.href for n in walk_components(offcanvas) if type(n).__name__ == "NavLink"
    ]
    assert "/projet/donnees" in hrefs
    assert not any("#" in href for href in hrefs)


def test_barre_laterale_desktop_liste_les_sous_sections():
    shell = _shell_donnees()
    offcanvas = next(
        n for n in walk_components(shell) if type(n).__name__ == "Offcanvas"
    )
    dans_offcanvas = {id(n) for n in walk_components(offcanvas)}
    hrefs = [
        n.href
        for n in walk_components(shell)
        if type(n).__name__ == "NavLink" and id(n) not in dans_offcanvas
    ]
    assert "/projet/donnees#champs" in hrefs
