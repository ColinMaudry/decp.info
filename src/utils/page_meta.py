"""Résolution chemin → métadonnées de page Dash, côté serveur.

Dash résout déjà titre et description par requête pour ses balises sociales
(`dash/_pages.py:_page_meta_tags`), mais passe `app.title` à `{%title%}` : le
`<title>` servi est donc générique sur toutes les pages. Ce module rejoue la
même résolution pour qu'`app.py` puisse la poser dans le HTML.

`resolve_title` ne résout QUE le titre, pas la description : `app.py` est le
seul appelant, et Dash calcule déjà la description lui-même dans
`_page_meta_tags` pour la balise `<meta name="description">`. Résoudre les
deux ici doublerait l'appel à `get_description`/`get_title` des pages
(acheteur, titulaire, marché) par requête HTTP — mesurable sur
`DF_ACHETEURS` à l'échelle production (242 005 lignes), et ces fonctions
tournent à chaque hit de crawler sur 1,5 million de fiches marché.

`_path_to_page` est une API privée de Dash, assumée : c'est la fonction que
Dash utilise lui-même pour router, et `src/not_found.py` s'y appuie déjà. Les
tests épinglent son comportement, donc une montée de version qui la
déplacerait casse la CI avant le déploiement.
"""

from dash._pages import _path_to_page


def page_for_path(path: str):
    """(page, variables de chemin) pour un chemin de requête."""
    return _path_to_page(path.strip("/"))


def resolve_title(path: str) -> str | None:
    """Titre résolu pour un chemin, None si le chemin ne correspond à aucune page."""
    page, path_variables = page_for_path(path)
    if not page:
        return None

    title = page.get("title")
    if not callable(title):
        return title
    return title(**path_variables) if path_variables else title()
