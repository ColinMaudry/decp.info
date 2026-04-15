import logging
import os
from pathlib import Path
from time import sleep

import duckdb
import polars as pl
import polars.selectors as cs
from polars.exceptions import ComputeError

logger = logging.getLogger("decp.info")


def should_rebuild(db_path: Path, parquet_path: Path) -> bool:
    db_path = Path(db_path)
    parquet_path = Path(parquet_path)
    if not db_path.exists():
        return True
    dev = os.getenv("DEVELOPMENT", "False").lower() == "true"
    force = os.getenv("REBUILD_DUCKDB", "False").lower() == "true"
    if dev and not force:
        return False
    return parquet_path.stat().st_mtime > db_path.stat().st_mtime


def _load_source_frame(parquet_path: Path) -> pl.DataFrame:
    """Read the source parquet and apply the row-level transforms.

    Kept here (not in utils.py) so src.db has no dependency on utils.
    Mirrors the behavior previously in utils.get_decp_data().
    """
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
        lff = lff.with_columns(
            pl.when(pl.col(col).is_null())
            .then(pl.lit("[Identifiant non reconnu dans la base INSEE]"))
            .otherwise(pl.col(col))
            .name.keep()
        )

    return lff.collect()


def build_database(db_path: Path, parquet_path: Path) -> None:
    """Build the DuckDB database atomically under an exclusive lock.

    Caller MUST hold the fcntl.flock on the .lock file.
    """
    db_path = Path(db_path)
    parquet_path = Path(parquet_path)
    tmp_path = db_path.with_suffix(".duckdb.tmp")
    staging_parquet = db_path.with_suffix(".staging.parquet")
    if tmp_path.exists():
        tmp_path.unlink()

    logger.info(f"Construction de la base DuckDB à partir de {parquet_path}...")
    frame = _load_source_frame(parquet_path)

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
