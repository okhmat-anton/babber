"""
Cloud Storage Service — S3-compatible file storage for multi-device usage.

Supports AWS S3, MinIO, DigitalOcean Spaces, Backblaze B2, etc.
"""
import io
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class S3Storage:
    """S3-compatible storage client using pre-signed URLs via boto3."""

    def __init__(self, endpoint_url: str, access_key: str, secret_key: str,
                 bucket: str, region: str = "us-east-1"):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.region = region
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            session = boto3.session.Session()
            self._client = session.client(
                "s3",
                endpoint_url=self.endpoint_url or None,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
            )
        return self._client

    async def check_connection(self) -> bool:
        """Test S3 connection by listing bucket (head_bucket)."""
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self.bucket)
            return True
        except Exception as e:
            logger.warning("S3 connection check failed: %s", e)
            return False

    async def upload_file(self, local_path: str, s3_key: str) -> bool:
        """Upload a local file to S3."""
        try:
            client = self._get_client()
            client.upload_file(local_path, self.bucket, s3_key)
            return True
        except Exception as e:
            logger.error("S3 upload failed for %s: %s", s3_key, e)
            return False

    async def upload_bytes(self, data: bytes, s3_key: str, content_type: str = "application/octet-stream") -> bool:
        """Upload bytes to S3."""
        try:
            client = self._get_client()
            client.put_object(Bucket=self.bucket, Key=s3_key, Body=data, ContentType=content_type)
            return True
        except Exception as e:
            logger.error("S3 upload_bytes failed for %s: %s", s3_key, e)
            return False

    async def download_file(self, s3_key: str, local_path: str) -> bool:
        """Download a file from S3 to local path."""
        try:
            client = self._get_client()
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            client.download_file(self.bucket, s3_key, local_path)
            return True
        except Exception as e:
            logger.error("S3 download failed for %s: %s", s3_key, e)
            return False

    async def download_bytes(self, s3_key: str) -> Optional[bytes]:
        """Download a file from S3 as bytes."""
        try:
            client = self._get_client()
            response = client.get_object(Bucket=self.bucket, Key=s3_key)
            return response["Body"].read()
        except Exception as e:
            logger.error("S3 download_bytes failed for %s: %s", s3_key, e)
            return None

    async def list_objects(self, prefix: str = "") -> list[dict]:
        """List objects in the bucket with optional prefix."""
        try:
            client = self._get_client()
            result = []
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    result.append({
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                    })
            return result
        except Exception as e:
            logger.error("S3 list failed for prefix %s: %s", prefix, e)
            return []

    async def delete_object(self, s3_key: str) -> bool:
        """Delete an object from S3."""
        try:
            client = self._get_client()
            client.delete_object(Bucket=self.bucket, Key=s3_key)
            return True
        except Exception as e:
            logger.error("S3 delete failed for %s: %s", s3_key, e)
            return False

    async def upload_directory(self, local_dir: str, s3_prefix: str) -> int:
        """Upload entire directory to S3. Returns count of uploaded files."""
        count = 0
        local_path = Path(local_dir)
        if not local_path.exists():
            return 0
        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(local_path)
                s3_key = f"{s3_prefix}/{rel_path}".replace("\\", "/")
                if await self.upload_file(str(file_path), s3_key):
                    count += 1
        return count

    async def download_directory(self, s3_prefix: str, local_dir: str) -> int:
        """Download all objects with prefix to local directory. Returns count."""
        count = 0
        objects = await self.list_objects(s3_prefix)
        for obj in objects:
            s3_key = obj["key"]
            rel_path = s3_key[len(s3_prefix):].lstrip("/")
            if not rel_path:
                continue
            local_path = os.path.join(local_dir, rel_path)
            if await self.download_file(s3_key, local_path):
                count += 1
        return count


def create_s3_client(settings: dict) -> Optional[S3Storage]:
    """Create S3Storage from settings dict."""
    endpoint = settings.get("s3_endpoint_url", "")
    access_key = settings.get("s3_access_key", "")
    secret_key = settings.get("s3_secret_key", "")
    bucket = settings.get("s3_bucket_name", "")
    region = settings.get("s3_region", "us-east-1")

    if not access_key or not secret_key or not bucket:
        return None

    return S3Storage(
        endpoint_url=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        bucket=bucket,
        region=region,
    )
