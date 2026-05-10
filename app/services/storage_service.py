"""
Storage abstraction — MinIO local / S3 AWS.

Chuyển đổi backend qua biến STORAGE_BACKEND ('minio' | 's3').
Singleton `storage_service` giữ nguyên interface cho caller.
"""

import asyncio
import io
import math
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Optional

from loguru import logger

from app.config import settings


class StorageBackend(ABC):
    """Abstract base class cho storage backends."""

    @abstractmethod
    async def ensure_bucket(self) -> None: ...

    @abstractmethod
    def upload_file(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...

    @abstractmethod
    def upload_stream(self, object_name: str, stream: io.IOBase, length: int, content_type: str = "application/octet-stream") -> str: ...

    async def upload_stream_async(self, object_name: str, stream: io.IOBase, length: int, content_type: str = "application/octet-stream") -> str:
        """Non-blocking wrapper cho upload_stream."""
        return await asyncio.to_thread(self.upload_stream, object_name, stream, length, content_type)

    @abstractmethod
    def download_file(self, object_name: str) -> bytes: ...

    @abstractmethod
    def delete_object(self, object_name: str) -> None: ...

    @abstractmethod
    def delete_prefix(self, prefix: str) -> None: ...

    @abstractmethod
    def get_presigned_url(self, object_name: str, expiry_hours: Optional[int] = None) -> str: ...

    @abstractmethod
    def get_download_url(self, object_name: str, expires_seconds: int = 3600) -> str: ...

    @abstractmethod
    def list_objects(self, prefix: str) -> list[dict]: ...


# ---------------------------------------------------------------------------
# MinIO Backend
# ---------------------------------------------------------------------------

class MinioBackend(StorageBackend):
    """MinIO local storage backend."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from minio import Minio
            self._client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
        return self._client

    @property
    def _bucket(self) -> str:
        return settings.minio_bucket

    async def ensure_bucket(self) -> None:
        from minio.error import S3Error
        try:
            if not self.client.bucket_exists(self._bucket):
                self.client.make_bucket(self._bucket)
                logger.info(f"Tạo MinIO bucket: {self._bucket}")
            else:
                logger.debug(f"MinIO bucket đã tồn tại: {self._bucket}")
        except S3Error as e:
            logger.error(f"Lỗi khởi tạo MinIO bucket: {e}")
            raise

    def upload_file(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(
            bucket_name=self._bucket,
            object_name=object_name,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        logger.debug(f"Uploaded {object_name} ({len(data)} bytes)")
        return object_name

    def upload_stream(self, object_name: str, stream: io.IOBase, length: int, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(
            bucket_name=self._bucket,
            object_name=object_name,
            data=stream,
            length=length,
            content_type=content_type,
        )
        return object_name

    def download_file(self, object_name: str) -> bytes:
        response = None
        try:
            response = self.client.get_object(self._bucket, object_name)
            return response.read()
        finally:
            if response:
                response.close()
                response.release_conn()

    def delete_object(self, object_name: str) -> None:
        self.client.remove_object(self._bucket, object_name)
        logger.debug(f"Deleted {object_name}")

    def delete_prefix(self, prefix: str) -> None:
        objects = self.client.list_objects(self._bucket, prefix=prefix, recursive=True)
        for obj in objects:
            self.client.remove_object(self._bucket, obj.object_name)
        logger.debug(f"Deleted prefix: {prefix}")

    def get_presigned_url(self, object_name: str, expiry_hours: Optional[int] = None) -> str:
        hours = expiry_hours or settings.minio_presign_expiry_hours
        return self.client.presigned_get_object(
            bucket_name=self._bucket,
            object_name=object_name,
            expires=timedelta(hours=hours),
        )

    def get_download_url(self, object_name: str, expires_seconds: int = 3600) -> str:
        return self.client.presigned_get_object(
            bucket_name=self._bucket,
            object_name=object_name,
            expires=timedelta(seconds=expires_seconds),
        )

    def list_objects(self, prefix: str) -> list[dict]:
        objects = self.client.list_objects(self._bucket, prefix=prefix, recursive=True)
        result = []
        for obj in objects:
            result.append({
                "name": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
            })
        return result


# ---------------------------------------------------------------------------
# S3 Backend (boto3)
# ---------------------------------------------------------------------------

class S3Backend(StorageBackend):
    """AWS S3 storage backend via boto3."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            kwargs = {
                "region_name": settings.s3_region,
                "use_ssl": settings.s3_use_ssl,
                "config": Config(
                    signature_version="s3v4",
                    s3={"addressing_style": settings.s3_addressing_style},
                ),
            }
            if settings.s3_endpoint_url:
                kwargs["endpoint_url"] = settings.s3_endpoint_url
            if settings.s3_access_key_id and settings.s3_secret_access_key:
                kwargs["aws_access_key_id"] = settings.s3_access_key_id
                kwargs["aws_secret_access_key"] = settings.s3_secret_access_key

            self._client = boto3.client("s3", **kwargs)
        return self._client

    @property
    def _bucket(self) -> str:
        return settings.s3_bucket

    async def ensure_bucket(self) -> None:
        def _ensure():
            try:
                self.client.head_bucket(Bucket=self._bucket)
                logger.debug(f"S3 bucket đã tồn tại: {self._bucket}")
            except self.client.exceptions.NoSuchBucket:
                self._create_bucket()
            except Exception as e:
                error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
                if error_code == "404":
                    self._create_bucket()
                else:
                    logger.error(f"Lỗi kiểm tra S3 bucket: {e}")
                    raise
        await asyncio.to_thread(_ensure)

    def _create_bucket(self):
        params = {"Bucket": self._bucket}
        if settings.s3_region != "us-east-1":
            params["CreateBucketConfiguration"] = {
                "LocationConstraint": settings.s3_region,
            }
        self.client.create_bucket(**params)
        logger.info(f"Tạo S3 bucket: {self._bucket}")

    def upload_file(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(
            Bucket=self._bucket,
            Key=object_name,
            Body=data,
            ContentType=content_type,
        )
        logger.debug(f"Uploaded {object_name} ({len(data)} bytes)")
        return object_name

    def upload_stream(self, object_name: str, stream: io.IOBase, length: int, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(
            Bucket=self._bucket,
            Key=object_name,
            Body=stream,
            ContentType=content_type,
            ContentLength=length,
        )
        return object_name

    def download_file(self, object_name: str) -> bytes:
        response = self.client.get_object(Bucket=self._bucket, Key=object_name)
        return response["Body"].read()

    def delete_object(self, object_name: str) -> None:
        self.client.delete_object(Bucket=self._bucket, Key=object_name)
        logger.debug(f"Deleted {object_name}")

    def delete_prefix(self, prefix: str) -> None:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            contents = page.get("Contents", [])
            if not contents:
                continue
            # Batch delete up to 1000 keys
            for i in range(0, len(contents), 1000):
                batch = contents[i:i + 1000]
                self.client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": obj["Key"]} for obj in batch]},
                )
        logger.debug(f"Deleted prefix: {prefix}")

    def get_presigned_url(self, object_name: str, expiry_hours: Optional[int] = None) -> str:
        hours = expiry_hours or settings.s3_presign_expiry_hours
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": object_name},
            ExpiresIn=hours * 3600,
        )

    def get_download_url(self, object_name: str, expires_seconds: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": object_name},
            ExpiresIn=expires_seconds,
        )

    def list_objects(self, prefix: str) -> list[dict]:
        result = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                result.append({
                    "name": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
                })
        return result


# ---------------------------------------------------------------------------
# Factory + Singleton
# ---------------------------------------------------------------------------

def _make_backend() -> StorageBackend:
    backend_name = settings.storage_backend.lower()
    if backend_name == "s3":
        logger.info("Storage backend in use: s3")
        return S3Backend()
    logger.info("Storage backend in use: minio")
    return MinioBackend()


storage_service = _make_backend()
