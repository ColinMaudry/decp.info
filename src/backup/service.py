import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from src.backup import crypto, naming, snapshot
from src.backup.config import BackupConfig
from src.backup.rotation import select_retained
from src.backup.storage import Storage

logger = logging.getLogger(__name__)


def _dated_keys(storage: Storage, prefix: str) -> list[tuple[str, datetime]]:
    dated: list[tuple[str, datetime]] = []
    for key in storage.list_keys(prefix):
        try:
            dated.append((key, naming.parse_timestamp(key)))
        except ValueError:
            continue
    return dated


def run_backup(config: BackupConfig, storage: Storage, now: datetime) -> str:
    data = snapshot.make_snapshot(config.db_path)
    encrypted = crypto.encrypt(data, config.encryption_key)
    key = naming.make_key(config.prefix, now)
    storage.upload_bytes(key, encrypted)

    dated = _dated_keys(storage, config.prefix)
    retained = select_retained((ts for _, ts in dated), now)
    for k, ts in dated:
        if ts not in retained:
            storage.delete(k)
    logger.info("Sauvegarde créée : %s", key)
    return key


def list_backups(config: BackupConfig, storage: Storage) -> list[tuple[str, datetime]]:
    dated = _dated_keys(storage, config.prefix)
    dated.sort(key=lambda item: item[1])
    return dated


def restore(config: BackupConfig, storage: Storage, key: str, now: datetime) -> Path:
    encrypted = storage.download_bytes(key)
    data = crypto.decrypt(encrypted, config.encryption_key)

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        snapshot.write_snapshot(data, tmp_path)
        if not snapshot.verify_integrity(tmp_path):
            raise ValueError(f"Sauvegarde corrompue, restauration annulée : {key}")

        db_path = config.db_path
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        backup_copy = db_path.with_name(f"{db_path.name}.bak-{stamp}")
        if db_path.exists():
            backup_copy.write_bytes(db_path.read_bytes())
        os.replace(tmp_path, db_path)
    except Exception:
        logger.error("Échec de la restauration depuis %s", key, exc_info=True)
        tmp_path.unlink(missing_ok=True)
        raise
    return backup_copy
