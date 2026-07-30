"""Reconstruction de la base quand le schéma des tables dérivées change.

Incident du 2026-07-30 : #128 a ajouté la colonne `nb_marches` aux tables
d'organismes sans toucher au parquet source. `should_rebuild` ne comparant que
les dates de fichiers, la production a gardé sa base à l'ancien schéma après
déploiement et les pages d'index ont répondu 500 jusqu'au rafraîchissement
quotidien du parquet.

Ces tests épinglent le mécanisme qui l'empêche : une version de schéma écrite
dans la base et comparée au démarrage.
"""

from pathlib import Path

import duckdb

from src.db import SCHEMA_VERSION, schema_est_perime, should_rebuild


def _base(tmp_path: Path, version: int | None = None) -> Path:
    """Base minimale, avec ou sans table de version."""
    chemin = tmp_path / "essai.duckdb"
    with duckdb.connect(str(chemin)) as c:
        c.execute("CREATE TABLE decp AS SELECT 1 AS x")
        if version is not None:
            c.execute(f"CREATE TABLE schema_version AS SELECT {version} AS version")
    return chemin


def test_base_sans_table_de_version_est_perimee(tmp_path):
    """Le cas exact de l'incident : base construite avant ce mécanisme."""
    assert schema_est_perime(_base(tmp_path)) is True


def test_base_a_une_version_anterieure_est_perimee(tmp_path):
    assert schema_est_perime(_base(tmp_path, SCHEMA_VERSION - 1)) is True


def test_base_a_la_bonne_version_est_a_jour(tmp_path):
    assert schema_est_perime(_base(tmp_path, SCHEMA_VERSION)) is False


def test_schema_perime_force_la_reconstruction_meme_en_dev(tmp_path, monkeypatch):
    """Le raccourci `DEVELOPMENT=true` ne doit pas court-circuiter ce contrôle.

    Une base au mauvais schéma est inutilisable par le code courant, quel que
    soit l'environnement : c'est pourquoi le contrôle précède le raccourci.
    """
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.delenv("REBUILD_DUCKDB", raising=False)
    assert should_rebuild(_base(tmp_path), "peu importe") is True


def test_la_base_construite_porte_la_version_courante():
    """`build_database` écrit bien la version : sinon chaque démarrage
    reconstruirait la base, ce qui passerait inaperçu en test mais coûterait
    plusieurs minutes à chaque redémarrage en production."""
    from src.db import DB_PATH

    with duckdb.connect(str(DB_PATH), read_only=True) as c:
        version = c.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == SCHEMA_VERSION
