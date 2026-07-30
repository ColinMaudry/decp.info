"""Résolution chemin → métadonnées de page Dash, côté serveur.

Dash résout déjà titre et description par requête pour ses balises sociales
(`dash/_pages.py:_page_meta_tags`), mais passe `app.title` à `{%title%}` : le
`<title>` servi est donc générique sur toutes les pages. Ce module rejoue la
même résolution pour qu'`app.py` puisse la poser dans le HTML.

`_path_to_page` est une API privée de Dash, assumée : c'est la fonction que
Dash utilise lui-même pour router, et `src/not_found.py` s'y appuie déjà. Les
tests épinglent son comportement, donc une montée de version qui la
déplacerait casse la CI avant le déploiement.
"""

from dash._pages import _path_to_page


def page_for_path(path: str):
    """(page, variables de chemin) pour un chemin de requête."""
    return _path_to_page(path.strip("/"))


def resolve(path: str) -> tuple[str | None, str | None]:
    """(titre, description) résolus pour un chemin, (None, None) si inconnu."""
    page, path_variables = page_for_path(path)
    if not page:
        return None, None

    def _call(value):
        if not callable(value):
            return value
        return value(**path_variables) if path_variables else value()

    return _call(page.get("title")), _call(page.get("description"))
