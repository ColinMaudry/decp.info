import threading
import uuid
from time import localtime

from httpx import post

from src.utils import logger
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
        # debug et non warning : ce chemin s'exécute par requête, une panne
        # Matomo prolongée logguerait sinon en continu. Trace laissée pour ne
        # pas répéter le silence total qui a caché l'incident #128.
        logger.debug("Matomo : échec d'envoi", exc_info=True)


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


def _envoyer_async(params: dict) -> threading.Thread | None:
    """Envoie en tâche de fond et retourne le thread (pour que les tests joignent).

    Un POST synchrone retarderait de plusieurs secondes la réponse 200 au
    webhook Frisbii, qui pourrait alors considérer la livraison en échec et
    réessayer — donc émettre l'événement en double.

    `threading.Thread(...).start()` peut lever (ex. RuntimeError sous
    épuisement de ressources) : sans ce try/except, l'exception remonterait
    jusqu'à `update_from_webhook` (src/subscriptions/db.py), ferait répondre
    500 à Frisbii, et déclencherait un nouveau essai — rejouant la transaction
    et l'événement. Aucun émetteur ne doit jamais lever.
    """
    try:
        thread = threading.Thread(target=_envoyer, args=(params,), daemon=True)
        thread.start()
    except Exception:  # noqa: BLE001
        logger.debug("Matomo : échec de démarrage du thread d'envoi", exc_info=True)
        return None
    return thread


def track_subscription_goal(
    action: str, plan: str | None = None, revenue: float | None = None
) -> None:
    """Événement de conversion d'abonnement (`subscription_trial`/`_active`).

    Sous TOUS_ABONNES, l'accès est offert et la souscription payante est
    désactivée : aucun essai ni abonnement ne doit être comptabilisé. L'import
    est fait dans le corps de la fonction, comme dans src/subscriptions/db.py:347 —
    la constante est figée à l'import de src.utils, donc seul l'import différé
    rend effectif le monkeypatch.setattr("src.utils.TOUS_ABONNES", …) des tests.
    """
    from src.utils import TOUS_ABONNES

    if TOUS_ABONNES:
        return
    params = {
        "rec": "1",
        "url": "https://colibre.fr/compte/abonnement",
        "e_c": "Abonnement",
        "e_a": action,
        **_horodatage(),
    }
    if plan:
        params["e_n"] = plan
    if revenue is not None:
        params["e_v"] = revenue
    _envoyer_async(params)
