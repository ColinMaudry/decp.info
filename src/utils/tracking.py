import os
import uuid
from time import localtime

from httpx import post

from src.utils import DEVELOPMENT


def track_search(query, category):
    if len(query) >= 4 and not DEVELOPMENT and os.getenv("MATOMO_DOMAIN"):
        url = "https://colibre.fr"
        params = {
            "idsite": os.getenv("MATOMO_ID_SITE"),
            "url": url,
            "rec": "1",
            "action_name": "search" if category == "home_page_search" else "filter",
            "search_cat": category,
            "rand": uuid.uuid4().hex,
            "apiv": "1",
            "h": localtime().tm_hour,
            "m": localtime().tm_min,
            "s": localtime().tm_sec,
            "search": query,
            "token_auth": os.getenv("MATOMO_TOKEN"),
        }
        post(
            url=f"https://{os.getenv('MATOMO_DOMAIN')}/matomo.php",
            params=params,
        ).raise_for_status()


def track_mcp_tool(tool_name: str, query: str | None = None) -> None:
    """Enregistre un appel d'outil MCP dans Matomo (best-effort, prod uniquement).

    `action_name="MCP / <tool>"`, `dimension1=<tool>`. Si l'outil porte une
    requête texte, elle est envoyée en `search`. Nécessite un Custom Dimension
    slot 1 (scope Action) configuré côté Matomo — sinon `dimension1` est ignoré.
    Ne lève jamais : une panne Matomo ne doit pas casser l'appel du tool.
    """
    if DEVELOPMENT or not os.getenv("MATOMO_DOMAIN"):
        return
    params = {
        "idsite": os.getenv("MATOMO_ID_SITE"),
        "url": "https://colibre.fr/_mcp",
        "rec": "1",
        "action_name": f"MCP / {tool_name}",
        "dimension1": tool_name,
        "rand": uuid.uuid4().hex,
        "apiv": "1",
        "h": localtime().tm_hour,
        "m": localtime().tm_min,
        "s": localtime().tm_sec,
        "token_auth": os.getenv("MATOMO_TOKEN"),
    }
    if query:
        params["search"] = query
        params["search_cat"] = "mcp"
    try:
        post(url=f"https://{os.getenv('MATOMO_DOMAIN')}/matomo.php", params=params)
    except Exception:
        pass
