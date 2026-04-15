import time

import pytest


@pytest.fixture
def parquet_and_db(tmp_path, monkeypatch):
    parquet = tmp_path / "source.parquet"
    db = tmp_path / "decp.duckdb"
    parquet.write_bytes(b"fake parquet content")
    monkeypatch.delenv("REBUILD_DUCKDB", raising=False)
    monkeypatch.delenv("DEVELOPMENT", raising=False)
    return parquet, db


def test_should_rebuild_when_db_missing(parquet_and_db, monkeypatch):
    from src.db import should_rebuild

    parquet, db = parquet_and_db
    monkeypatch.setenv("DEVELOPMENT", "true")
    assert should_rebuild(db, parquet) is True


def test_should_rebuild_prod_when_parquet_newer(parquet_and_db, monkeypatch):
    from src.db import should_rebuild

    parquet, db = parquet_and_db
    db.write_bytes(b"x")
    time.sleep(0.01)
    parquet.touch()
    monkeypatch.setenv("DEVELOPMENT", "false")
    assert should_rebuild(db, parquet) is True


def test_should_not_rebuild_prod_when_parquet_older(parquet_and_db, monkeypatch):
    from src.db import should_rebuild

    parquet, db = parquet_and_db
    parquet.touch()
    time.sleep(0.01)
    db.write_bytes(b"x")
    monkeypatch.setenv("DEVELOPMENT", "false")
    assert should_rebuild(db, parquet) is False


def test_should_not_rebuild_dev_even_when_parquet_newer(parquet_and_db, monkeypatch):
    from src.db import should_rebuild

    parquet, db = parquet_and_db
    db.write_bytes(b"x")
    time.sleep(0.01)
    parquet.touch()
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.delenv("REBUILD_DUCKDB", raising=False)
    assert should_rebuild(db, parquet) is False


def test_should_rebuild_dev_when_rebuild_forced(parquet_and_db, monkeypatch):
    from src.db import should_rebuild

    parquet, db = parquet_and_db
    db.write_bytes(b"x")
    time.sleep(0.01)
    parquet.touch()
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setenv("REBUILD_DUCKDB", "true")
    assert should_rebuild(db, parquet) is True
