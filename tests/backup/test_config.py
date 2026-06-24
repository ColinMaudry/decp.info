from pathlib import Path

from src.backup.config import BackupConfig, load_config


def test_load_config_reads_env():
    env = {
        "USERS_DB_PATH": "users.sqlite",
        "S3_BUCKET": "decp-backups",
        "S3_BACKUP_PREFIX": "backups",
        "S3_ENDPOINT_URL": "https://s3.example.net",
        "S3_ACCESS_KEY_ID": "AK",
        "S3_SECRET_ACCESS_KEY": "SK",
        "BACKUP_ENCRYPTION_KEY": "key123",
    }
    cfg = load_config(env)
    assert cfg == BackupConfig(
        db_path=Path("users.sqlite"),
        bucket="decp-backups",
        prefix="backups",
        endpoint_url="https://s3.example.net",
        access_key="AK",
        secret_key="SK",
        encryption_key="key123",
    )


def test_load_config_defaults_prefix_and_empty_endpoint():
    env = {
        "USERS_DB_PATH": "users.sqlite",
        "S3_BUCKET": "b",
        "S3_ENDPOINT_URL": "",
        "S3_ACCESS_KEY_ID": "AK",
        "S3_SECRET_ACCESS_KEY": "SK",
        "BACKUP_ENCRYPTION_KEY": "k",
    }
    cfg = load_config(env)
    assert cfg.prefix == "backups"
    assert cfg.endpoint_url is None
