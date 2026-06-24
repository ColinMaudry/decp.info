import boto3
import pytest
from moto import mock_aws

from src.backup.storage import S3Storage

BUCKET = "decp-backups"


@pytest.fixture
def s3_storage():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield S3Storage(
            bucket=BUCKET,
            endpoint_url=None,
            access_key="testing",
            secret_key="testing",
        )


def test_upload_list_download_delete(s3_storage):
    s3_storage.upload_bytes("backups/a.enc", b"alpha")
    s3_storage.upload_bytes("backups/b.enc", b"beta")
    s3_storage.upload_bytes("autre/c.enc", b"gamma")

    assert set(s3_storage.list_keys("backups/")) == {"backups/a.enc", "backups/b.enc"}
    assert s3_storage.download_bytes("backups/a.enc") == b"alpha"

    s3_storage.delete("backups/a.enc")
    assert s3_storage.list_keys("backups/") == ["backups/b.enc"]
