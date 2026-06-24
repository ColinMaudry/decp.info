import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet

from src.backup import cli
from tests.backup.fakes import FakeStorage


def _env(tmp_path: Path) -> dict:
    db = tmp_path / "users.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (val TEXT)")
    conn.execute("INSERT INTO t VALUES ('v1')")
    conn.commit()
    conn.close()
    return {
        "USERS_DB_PATH": str(db),
        "S3_BUCKET": "b",
        "S3_BACKUP_PREFIX": "backups",
        "S3_ENDPOINT_URL": "",
        "S3_ACCESS_KEY_ID": "AK",
        "S3_SECRET_ACCESS_KEY": "SK",
        "BACKUP_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    }


def test_backup_then_list(tmp_path, capsys):
    env = _env(tmp_path)
    storage = FakeStorage()
    assert cli.main(["backup"], env=env, storage=storage) == 0
    assert cli.main(["list"], env=env, storage=storage) == 0
    out = capsys.readouterr().out
    assert "users-" in out
    assert len(storage.objects) == 1


def test_restore(tmp_path):
    env = _env(tmp_path)
    storage = FakeStorage()
    # Create a backup first
    assert cli.main(["backup"], env=env, storage=storage) == 0
    key = next(iter(storage.objects))
    # Restore it
    ret = cli.main(["restore", key], env=env, storage=storage)
    assert ret == 0
