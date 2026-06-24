from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BackupConfig:
    db_path: Path
    bucket: str
    prefix: str
    endpoint_url: str | None
    access_key: str
    secret_key: str
    encryption_key: str


def load_config(env: Mapping[str, str]) -> BackupConfig:
    return BackupConfig(
        db_path=Path(env["USERS_DB_PATH"]),
        bucket=env["S3_BUCKET"],
        prefix=env.get("S3_BACKUP_PREFIX", "backups"),
        endpoint_url=env.get("S3_ENDPOINT_URL") or None,
        access_key=env["S3_ACCESS_KEY_ID"],
        secret_key=env["S3_SECRET_ACCESS_KEY"],
        encryption_key=env["BACKUP_ENCRYPTION_KEY"],
    )
