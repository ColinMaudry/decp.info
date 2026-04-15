import logging
import os
from pathlib import Path

logger = logging.getLogger("decp.info")


def should_rebuild(db_path: Path, parquet_path: Path) -> bool:
    """Decide whether to rebuild the DuckDB database from the source Parquet.

    Rules:
      - Rebuild if the DuckDB file does not exist.
      - Otherwise, rebuild only if the source Parquet is newer than the DB,
        EXCEPT in development mode without REBUILD_DUCKDB=true (dev keeps
        a stable DB across reloads unless explicitly opted in).
    """
    db_path = Path(db_path)
    parquet_path = Path(parquet_path)

    if not db_path.exists():
        return True

    dev = os.getenv("DEVELOPMENT", "False").lower() == "true"
    force = os.getenv("REBUILD_DUCKDB", "False").lower() == "true"
    if dev and not force:
        return False

    return parquet_path.stat().st_mtime > db_path.stat().st_mtime
