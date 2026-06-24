from typing import Protocol

import boto3

from src.backup.config import BackupConfig


class Storage(Protocol):
    def upload_bytes(self, key: str, data: bytes) -> None: ...
    def download_bytes(self, key: str) -> bytes: ...
    def list_keys(self, prefix: str) -> list[str]: ...
    def delete(self, key: str) -> None: ...


class S3Storage:
    def __init__(
        self, bucket, endpoint_url, access_key, secret_key, region="us-east-1"
    ):
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    @classmethod
    def from_config(cls, config: BackupConfig) -> "S3Storage":
        return cls(
            bucket=config.bucket,
            endpoint_url=config.endpoint_url,
            access_key=config.access_key,
            secret_key=config.secret_key,
        )

    def upload_bytes(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def download_bytes(self, key: str) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
