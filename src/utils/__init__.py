import logging
import os
from datetime import datetime
from pathlib import Path

import httpx

from src.utils.cache import cache


@cache.memoize()
def get_last_modified(parquet_path: str) -> float:
    logger.info("Récupération de la date de modification des données...")
    logging.getLogger("httpx").setLevel("WARNING")
    if parquet_path.startswith("http"):
        last_modified = httpx.head(
            url=parquet_path,
            follow_redirects=True,
        ).headers["last-modified"]
        last_modified = datetime.strptime(last_modified, "%a, %d %b %Y %X %Z").strftime(
            "%s"
        )
        return float(last_modified)
    parquet_local_path = Path(parquet_path)
    return parquet_local_path.stat().st_mtime


logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
DEVELOPMENT = os.getenv("DEVELOPMENT", "False").lower() == "true"
logger = logging.getLogger("decp.info")

if DEVELOPMENT:
    logger.setLevel(logging.DEBUG)

DOMAIN_NAME = (
    "test.decp.info"
    if os.getenv("DEVELOPMENT", "False").lower() == "true"
    else "decp.info"
)
