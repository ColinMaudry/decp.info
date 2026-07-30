"""Statut HTTP 404 pour les chemins qui ne correspondent à aucune page (#125).

Dash enregistre un catch-all `<path:path>` (`dash/backends/_flask.py:191`) qui
sert la coquille HTML de l'index pour n'importe quel chemin, le routage des
pages étant fait côté client. Résultat : `/db`, hérité de l'ancien decp.info,
répondait 200 comme tout le reste.

Ce module intercepte ces requêtes avant le rendu et répond `assets/404.html`
avec le bon statut. La navigation interne de la SPA, elle, ne repasse pas par
le serveur : elle est couverte par `src/pages/not_found_404.py`.
"""

import os

# Passe par src.utils.page_meta, qui porte désormais la justification de l'appel
# à l'API privée `_path_to_page` de Dash (assumée : c'est la fonction que Dash
# utilise lui-même pour router, donc la seule façon de renvoyer 404 exactement
# sur ce qu'il aurait affiché comme introuvable, gabarits compris
# (`/marches/<uid>`)).
from flask import Flask, request, send_from_directory

from src.utils.page_meta import page_for_path

# Règle Flask du catch-all de Dash. Les vraies routes (/robots.txt, /api/…,
# /assets/<path:filename>, /_dash-*, /_mcp, /oauth/*, /.well-known/*) ont la
# leur, donc elles ne passent jamais par ici et gardent leurs propres 404.
_CATCHALL_RULE = "/<path:path>"

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
_PAGE_404 = "404.html"


def page_exists(pathname: str) -> bool:
    """Le chemin correspond-il à une page Dash affichable ?

    La page `not_found_404` compte comme absente : son URL propre doit répondre
    404 elle aussi, sans quoi on servirait un message « page introuvable » avec
    un statut 200.
    """
    page, _ = page_for_path(pathname)
    if not page:
        return False
    return page["module"].split(".")[-1] != "not_found_404"


def init_not_found(server: Flask) -> None:
    @server.before_request
    def _not_found_for_unknown_paths():
        if request.url_rule is None or request.url_rule.rule != _CATCHALL_RULE:
            return None
        if page_exists(request.path):
            return None
        response = send_from_directory(_ASSETS_DIR, _PAGE_404)
        response.status_code = 404
        return response
