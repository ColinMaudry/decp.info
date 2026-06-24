import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from src.backup import service
from src.backup.config import BackupConfig
from src.backup.naming import make_key
from tests.backup.fakes import FakeStorage

NOW = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)


def _make_db(path: Path, val: str):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (val TEXT)")
    conn.execute("INSERT INTO t VALUES (?)", (val,))
    conn.commit()
    conn.close()


def _config(db_path: Path) -> BackupConfig:
    return BackupConfig(
        db_path=db_path,
        bucket="b",
        prefix="backups",
        endpoint_url=None,
        access_key="AK",
        secret_key="SK",
        encryption_key=Fernet.generate_key().decode(),
    )


def test_run_backup_uploads_key(tmp_path):
    db = tmp_path / "users.sqlite"
    _make_db(db, "v1")
    storage = FakeStorage()
    key = service.run_backup(_config(db), storage, NOW)
    assert key in storage.objects
    assert key == "backups/users-20260624T120000Z.sqlite.gz.enc"


def test_run_backup_applies_rotation(tmp_path):
    db = tmp_path / "users.sqlite"
    _make_db(db, "v1")
    cfg = _config(db)
    storage = FakeStorage()
    # une vieille sauvegarde de >12 mois doit être supprimée par la rotation
    stale = make_key(cfg.prefix, NOW - timedelta(days=400))
    storage.objects[stale] = b"old"
    service.run_backup(cfg, storage, NOW)
    assert stale not in storage.objects


def test_list_backups_sorted(tmp_path):
    db = tmp_path / "users.sqlite"
    _make_db(db, "v1")
    cfg = _config(db)
    storage = FakeStorage()
    storage.objects[make_key(cfg.prefix, NOW)] = b"x"
    storage.objects[make_key(cfg.prefix, NOW - timedelta(hours=1))] = b"x"
    storage.objects["backups/garbage.txt"] = b"x"  # ignoré
    result = service.list_backups(cfg, storage)
    dates = [ts for _, ts in result]
    assert dates == sorted(dates)
    assert len(result) == 2


def test_restore_replaces_db_and_keeps_safety_copy(tmp_path):
    db = tmp_path / "users.sqlite"
    _make_db(db, "original")
    cfg = _config(db)
    storage = FakeStorage()
    key = service.run_backup(cfg, storage, NOW)  # sauvegarde "original"

    # la base change ensuite
    db.unlink()
    _make_db(db, "modifie")

    backup_copy = service.restore(cfg, storage, key, NOW)

    conn = sqlite3.connect(str(db))
    val = conn.execute("SELECT val FROM t").fetchone()[0]
    conn.close()
    assert val == "original"
    assert backup_copy.exists()  # copie de secours de la base "modifie"


def test_restore_rejects_corrupt_backup(tmp_path):
    db = tmp_path / "users.sqlite"
    _make_db(db, "original")
    cfg = _config(db)
    storage = FakeStorage()
    from src.backup import crypto

    bad_key = make_key(cfg.prefix, NOW)
    import gzip

    storage.objects[bad_key] = crypto.encrypt(
        gzip.compress(b"not sqlite"), cfg.encryption_key
    )
    with pytest.raises(ValueError):
        service.restore(cfg, storage, bad_key, NOW)
