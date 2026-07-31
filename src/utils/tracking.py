import uuid
from time import localtime

from httpx import post

from src.utils.matomo import matomo_config, tracking_enabled


def _envoyer(params: dict) -> None:
    """POST best-effort vers la Tracking API Matomo. Ne lève jamais.

    `data=` et non `params=` : la charge utile passe dans le corps de la requête
    plutôt que dans la query string, où elle atterrirait dans les journaux
    d'accès du serveur Matomo.

    Aucun `token_auth` : l'endpoint matomo.php est public par construction —
    c'est celui qu'appelle le matomo.js de chaque visiteur. Le token n'est
    requis que pour les paramètres privilégiés (cip, cdt au-delà de ~24 h,
    country/region/city/lat/long), qu'aucun émetteur du projet n'utilise.
    """
    if not tracking_enabled():
        return
    config = matomo_config()
    if config is None:
        return
    url, site_id = config
    try:
        # timeout court : track_search s'exécute de façon synchrone dans une
        # recherche utilisateur (src/utils/search.py), un Matomo qui pend ne
        # doit pas ajouter sa latence à la requête de l'utilisateur.
        post(url=url, data={**params, "idsite": site_id}, timeout=2.0)
    except Exception:  # noqa: BLE001
        pass


def _horodatage() -> dict:
    maintenant = localtime()
    return {
        "rand": uuid.uuid4().hex,
        "apiv": "1",
        "h": maintenant.tm_hour,
        "m": maintenant.tm_min,
        "s": maintenant.tm_sec,
    }


def track_search(query, category):
    """Enregistre une recherche dans Matomo (best-effort)."""
    if len(query) < 4:
        return
    _envoyer(
        {
            "rec": "1",
            "url": "https://colibre.fr",
            "action_name": "search" if category == "home_page_search" else "filter",
            "search_cat": category,
            "search": query,
            **_horodatage(),
        }
    )


def track_mcp_tool(tool_name: str, query: str | None = None) -> None:
    """Enregistre un appel d'outil MCP dans Matomo (best-effort).

    `action_name="MCP / <tool>"`, `dimension1=<tool>`. Si l'outil porte une
    requête texte, elle est envoyée en `search`. Nécessite un Custom Dimension
    slot 1 (scope Action) configuré côté Matomo — sinon `dimension1` est ignoré.
    """
    params = {
        "rec": "1",
        "url": "https://colibre.fr/_mcp",
        "action_name": f"MCP / {tool_name}",
        "dimension1": tool_name,
        **_horodatage(),
    }
    if query:
        params["search"] = query
        params["search_cat"] = "mcp"
    _envoyer(params)
