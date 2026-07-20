import fcntl
import os
import re
from pathlib import Path
from time import sleep

import duckdb
import polars as pl
import polars.selectors as cs
from polars.exceptions import ComputeError

from src.utils import get_last_modified, logger

# Format accepté par DuckDB pour memory_limit, ex. « 2GB », « 512MiB ».
# Validé plutôt qu'interpolé tel quel : SET n'accepte pas de paramètre lié.
_MEMORY_LIMIT_RE = re.compile(r"^\d+(\.\d+)?\s*(B|[KMGT]B|[KMGT]iB)$", re.IGNORECASE)


def configure_connection(conn: duckdb.DuckDBPyConnection) -> None:
    """Borne les ressources de l'instance DuckDB de ce processus.

    Les défauts DuckDB (`threads` = tous les cœurs, `memory_limit` = 80 % de la
    RAM) s'appliquent **par processus** et ignorent les limites cgroup. Avec
    plusieurs workers gunicorn, chaque processus croit donc disposer de la
    machine entière, ce qui mène à la sursouscription CPU et à l'OOM kill.

    Ces réglages valent pour l'instance, pas par requête : les curseurs rendus
    par `get_cursor()` partagent le même ordonnanceur. Le plafond CPU d'un
    conteneur vaut donc `workers × DUCKDB_THREADS`.

    Sans variable d'environnement, les défauts DuckDB sont préservés (on ne
    change pas le comportement d'un déploiement existant), mais l'absence de
    bornage est signalée dans les logs.
    """
    threads = os.getenv("DUCKDB_THREADS", "").strip()
    memory_limit = os.getenv("DUCKDB_MEMORY_LIMIT", "").strip()

    if threads:
        conn.execute(f"SET threads = {int(threads)}")
    if memory_limit:
        if not _MEMORY_LIMIT_RE.match(memory_limit):
            raise ValueError(
                f"DUCKDB_MEMORY_LIMIT invalide : {memory_limit!r} "
                "(format attendu, ex. « 2GB » ou « 512MiB »)"
            )
        conn.execute(f"SET memory_limit = '{memory_limit}'")

    if not threads or not memory_limit:
        actuel_threads = conn.execute("SELECT current_setting('threads')").fetchone()[0]
        actuel_memoire = conn.execute(
            "SELECT current_setting('memory_limit')"
        ).fetchone()[0]
        logger.warning(
            "DuckDB non borné (DUCKDB_THREADS / DUCKDB_MEMORY_LIMIT) : ce processus "
            f"utilisera jusqu'à {actuel_threads} threads et {actuel_memoire}. "
            "Ces limites s'appliquent par worker : à définir en production."
        )


def should_rebuild(db_path: Path, parquet_path: str) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        logger.info("Fichier DuckDB inexistant.")
        return True
    dev = os.getenv("DEVELOPMENT", "False").lower() == "true"
    force = os.getenv("REBUILD_DUCKDB", "False").lower() == "true"
    if dev and not force:
        return False
    last_modified: float = get_last_modified(parquet_path)
    fresh_parquet = last_modified > db_path.stat().st_mtime
    logger.info(f"Parquet plus récent : {str(fresh_parquet)}")
    return fresh_parquet


def _load_source_frame() -> pl.DataFrame:
    """Read the source parquet and apply the row-level transforms.

    Kept here (not in utils.py) so src.db has no dependency on utils.
    Mirrors the behavior previously in utils.get_decp_data().
    """

    parquet_path: str = os.getenv("DATA_FILE_PARQUET_PATH", "")
    if not (parquet_path.startswith("http")):
        assert os.path.exists(parquet_path)
    try:
        lff: pl.LazyFrame = pl.scan_parquet(str(parquet_path))
    except ComputeError:
        logger.info("Lecture du parquet échouée, nouvelle tentative dans 10s...")
        sleep(10)
        lff = pl.scan_parquet(str(parquet_path))

    lff = lff.sort(by=["dateNotification", "uid"], descending=True, nulls_last=True)
    lff = lff.filter(pl.col("donneesActuelles")).drop("donneesActuelles")

    # booleans_to_strings: true → "oui", false → "non"
    lff = lff.with_columns(
        pl.col(cs.Boolean)
        .cast(pl.String)
        .str.replace("true", "oui")
        .str.replace("false", "non")
    )

    for col in ["acheteur_nom", "titulaire_nom"]:
        id_col = col.replace("_nom", "_id")
        lff = lff.with_columns(
            pl.when(pl.col(col).is_null())
            .then(
                pl.concat_str(
                    [
                        pl.lit("[Inconnu de l'INSEE ("),
                        pl.col(id_col).cast(pl.String),
                        pl.lit(")]"),
                    ]
                )
            )
            .otherwise(pl.col(col))
            # .alias(col) explicite : avec .name.keep(), Polars nomme le résultat
            # d'après id_col (référencé dans concat_str), ce qui écrasait la
            # colonne *_id et laissait *_nom inchangé au lieu de l'inverse.
            .alias(col)
        )

    return lff.collect()


def build_database(db_path: Path) -> None:
    """Build the DuckDB database atomically under an exclusive lock.

    Caller MUST hold the fcntl.flock on the .lock file.
    """
    db_path = Path(db_path)
    tmp_path = db_path.with_suffix(".duckdb.tmp")
    staging_parquet = db_path.with_suffix(".staging.parquet")
    if tmp_path.exists():
        tmp_path.unlink()

    logger.info(
        f"Construction de la base DuckDB à partir de {os.getenv('DATA_FILE_PARQUET_PATH', '')}..."
    )
    frame = _load_source_frame()

    # Write transformed frame as parquet so DuckDB can read it natively
    # (avoids pyarrow dependency for the Polars→DuckDB handoff)
    frame.write_parquet(str(staging_parquet))
    try:
        with duckdb.connect(str(tmp_path)) as w:
            w.execute(
                f"CREATE TABLE decp AS SELECT * FROM read_parquet('{staging_parquet}')"
            )
            w.execute(
                "CREATE TABLE acheteurs_marches AS "
                "SELECT DISTINCT uid, objet, acheteur_id FROM decp "
                "ORDER BY acheteur_id"
            )
            w.execute(
                "CREATE TABLE titulaires_marches AS "
                "SELECT DISTINCT uid, objet, titulaire_id FROM decp "
                "ORDER BY titulaire_id"
            )
            w.execute(
                "CREATE TABLE acheteurs_departement AS "
                "SELECT DISTINCT acheteur_id, acheteur_nom, acheteur_departement_code "
                "FROM decp ORDER BY acheteur_nom"
            )
            w.execute(
                "CREATE TABLE titulaires_departement AS "
                "SELECT DISTINCT titulaire_id, titulaire_nom, titulaire_departement_code "
                "FROM decp ORDER BY titulaire_nom"
            )
    finally:
        if staging_parquet.exists():
            staging_parquet.unlink()

    os.replace(tmp_path, db_path)
    logger.info(f"Base DuckDB construite : {db_path}")


def _ensure_database() -> Path:
    db_path = Path(os.getenv("DUCKDB_PATH", "./decp.duckdb"))
    parquet_path = os.getenv("DATA_FILE_PARQUET_PATH", "")
    lock_path = db_path.with_suffix(".duckdb.lock")
    db_exists = db_path.exists()

    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            if should_rebuild(db_path, parquet_path):
                build_database(db_path)
            else:
                logger.debug("Base de données déjà disponible et à jour.")
        except Exception as e:
            if db_exists and db_path.exists():
                logger.error(
                    f"Bootstrap données KO ({e}). "
                    f"Réutilisation du DuckDB existant : {db_path}"
                )
            else:
                logger.critical("Aucune base DuckDB et reconstruction impossible.")
                raise
    return db_path


DB_PATH = _ensure_database()
conn: duckdb.DuckDBPyConnection = duckdb.connect(str(DB_PATH), read_only=True)
configure_connection(conn)
schema: pl.Schema = conn.execute("SELECT * FROM decp LIMIT 0").pl().schema


def get_cursor() -> duckdb.DuckDBPyConnection:
    """Return a per-request cursor that shares the process-wide connection."""
    return conn.cursor()


def query_marches(
    where_sql: str = "TRUE",
    params: tuple | list = (),
    columns: list[str] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> pl.DataFrame:
    """Run a parameterized SELECT against the decp table and return Polars.

    `where_sql` and `order_by` are trusted SQL fragments (callers are internal
    code, never user input). `params` values are passed through DuckDB's
    parameter binding.
    """
    cols = ", ".join(columns) if columns else "*"
    sql = f"SELECT {cols} FROM decp WHERE {where_sql}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    if offset is not None:
        sql += f" OFFSET {int(offset)}"

    logger.debug("query_marches: " + sql.replace("?", "{}").format(*params))

    return get_cursor().execute(sql, list(params)).pl()


def count_marches(where_sql: str = "TRUE", params: tuple | list = ()) -> int:
    """Retourne le nombre de lignes correspondant à where_sql."""
    sql = f"SELECT COUNT(*) FROM decp WHERE {where_sql}"
    logger.debug("count_marches: " + sql.replace("?", "{}").format(*params))
    result = get_cursor().execute(sql, list(params)).fetchone()
    return int(result[0]) if result else 0


def count_unique_marches(where_sql: str = "TRUE", params: tuple | list = ()) -> int:
    """Retourne le nombre de uid distincts correspondant à where_sql."""
    sql = f"SELECT COUNT(DISTINCT uid) FROM decp WHERE {where_sql}"
    logger.debug("count_unique_marches: " + sql.replace("?", "{}").format(*params))
    result = get_cursor().execute(sql, list(params)).fetchone()
    return int(result[0]) if result else 0


def aggregate_marches(
    select_sql: str,
    where_sql: str = "TRUE",
    params: tuple | list = (),
    group_by: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> pl.DataFrame:
    """SELECT agrégé paramétré contre la table decp.

    `select_sql`, `group_by` et `order_by` sont des fragments SQL construits
    depuis des noms de colonnes validés (jamais de valeur utilisateur libre).
    Les valeurs de filtre passent par le binding `?` via `params`.
    """
    sql = f"SELECT {select_sql} FROM decp WHERE {where_sql}"
    if group_by:
        sql += f" GROUP BY {group_by}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    if offset is not None:
        sql += f" OFFSET {int(offset)}"

    logger.debug("aggregate_marches: " + sql.replace("?", "{}").format(*params))

    return get_cursor().execute(sql, list(params)).pl()
