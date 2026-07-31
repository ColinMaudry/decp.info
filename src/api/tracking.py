import queue
import threading
from typing import Optional

import httpx

from src.api import tokens_db
from src.utils import logger
from src.utils.matomo import matomo_config, tracking_enabled

_STOP_SENTINEL = object()
_queue: Optional[queue.Queue] = None
_worker_thread: Optional[threading.Thread] = None


def _worker_loop(q: queue.Queue, db_path: str) -> None:
    while True:
        item = q.get()
        try:
            if item is _STOP_SENTINEL:
                return
            kind, payload = item
            if kind == "counter":
                token_id = payload
                try:
                    tokens_db.increment_usage(db_path, token_id)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "tracking: échec increment_usage token_id=%s",
                        token_id,
                        exc_info=True,
                    )
            elif kind == "matomo":
                try:
                    _post_matomo(**payload)
                except Exception:  # noqa: BLE001
                    logger.warning("tracking: échec envoi Matomo", exc_info=True)
        finally:
            q.task_done()


def _post_matomo(url: str, params: dict) -> None:
    """POST fire-and-forget vers la Tracking API Matomo. Mockable en test."""
    httpx.post(url, data=params, timeout=5.0)


def enqueue_matomo_event(
    token_id: int,
    path: str,
    query_string: str,
    status_code: int,
    user_agent: str,
) -> None:
    if _queue is None:
        return
    # Garde commune aux quatre points d'émission Matomo du projet
    # (src/utils/matomo.py) : elle combine DEVELOPMENT et
    # MATOMO_TRACKING_ENABLED. La couper éteint toute l'analytique du site,
    # pas seulement celle de l'API.
    if not tracking_enabled():
        return
    config = matomo_config()
    if config is None:
        return
    url, site_id = config
    full_url = f"https://colibre.fr{path}"
    if query_string:
        full_url += f"?{query_string}"
    params = {
        "idsite": site_id,
        "rec": "1",
        "url": full_url,
        "action_name": f"API {path}",
        "uid": f"token-{token_id}",
        "dimension1": str(token_id),
        "dimension2": str(status_code),
        "ua": user_agent,
    }
    _queue.put(("matomo", {"url": url, "params": params}))


def start_worker(db_path: str) -> None:
    global _queue, _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _queue = queue.Queue()
    _worker_thread = threading.Thread(
        target=_worker_loop, args=(_queue, db_path), daemon=True
    )
    _worker_thread.start()


def stop_worker() -> None:
    global _worker_thread, _queue
    if _worker_thread is None:
        return
    _queue.put(_STOP_SENTINEL)
    _worker_thread.join(timeout=2.0)
    _worker_thread = None
    _queue = None


def enqueue_counter_update(token_id: int) -> None:
    if _queue is None:
        return  # tracking désactivé (tests par ex.)
    _queue.put(("counter", token_id))


def flush(timeout: float = 2.0) -> None:
    """Attend que la queue soit drainée. Utile en test."""
    q = _queue
    if q is None:
        return
    q.join()
