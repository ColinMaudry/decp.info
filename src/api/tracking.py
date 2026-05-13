import queue
import threading
from typing import Optional

from src.api import tokens_db
from src.utils import logger

_STOP_SENTINEL = object()
_queue: Optional[queue.Queue] = None
_worker_thread: Optional[threading.Thread] = None
_db_path: Optional[str] = None


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
        finally:
            q.task_done()


def start_worker(db_path: str) -> None:
    global _queue, _worker_thread, _db_path
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _db_path = db_path
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
    if _queue is None:
        return
    _queue.join()
