"""Object storage abstraction — pluggable backends (Local / S3 / MinIO)."""
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Protocol

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    async def upload(self, key: str, file_path: str, content_type: str = "") -> str:
        ...
    async def download(self, key: str, dest_path: str) -> str:
        ...
    async def delete(self, key: str) -> bool:
        ...
    async def presigned_url(self, key: str, expires_seconds: int = 3600) -> str:
        ...


class LocalStorageBackend:
    """Dev backend: local filesystem."""
    def __init__(self, base_dir: str = "storage"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    async def upload(self, key: str, file_path: str, content_type: str = "") -> str:
        import shutil
        dest = os.path.join(self.base_dir, key)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(file_path, dest)
        return dest

    async def download(self, key: str, dest_path: str) -> str:
        src = os.path.join(self.base_dir, key)
        import shutil
        shutil.copy2(src, dest_path)
        return dest_path

    async def delete(self, key: str) -> bool:
        path = os.path.join(self.base_dir, key)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    async def presigned_url(self, key: str, expires_seconds: int = 3600) -> str:
        return f"file://{os.path.join(self.base_dir, key)}"


class S3StorageBackend:
    """S3-compatible backend (AWS S3 / MinIO / 阿里云 OSS)."""
    def __init__(self, bucket: str, region: str, access_key: str, secret_key: str,
                 endpoint_url: str = ""):
        self.bucket = bucket
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint_url = endpoint_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "s3", region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                endpoint_url=self.endpoint_url or None,
            )
        return self._client

    async def upload(self, key: str, file_path: str, content_type: str = "") -> bool:
        s3 = self._get_client()
        extra = {"ContentType": content_type} if content_type else {}
        s3.upload_file(file_path, self.bucket, key, ExtraArgs=extra)
        logger.info(f"Uploaded s3://{self.bucket}/{key}")
        return True

    async def download(self, key: str, dest_path: str) -> str:
        s3 = self._get_client()
        s3.download_file(self.bucket, key, dest_path)
        return dest_path

    async def delete(self, key: str) -> bool:
        s3 = self._get_client()
        s3.delete_object(Bucket=self.bucket, Key=key)
        return True

    async def presigned_url(self, key: str, expires_seconds: int = 3600) -> str:
        s3 = self._get_client()
        return s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )


def get_storage_backend() -> StorageBackend:
    from src.config import settings
    backend = getattr(settings, "storage_backend", "local")
    if backend == "s3":
        return S3StorageBackend(
            bucket=settings.s3_bucket, region=settings.s3_region,
            access_key=settings.s3_access_key, secret_key=settings.s3_secret_key,
            endpoint_url=getattr(settings, "s3_endpoint_url", ""),
        )
    return LocalStorageBackend()
