"""
GramCare – MinIO / S3 storage service
Provides presigned upload/download URLs for direct client uploads.
"""

import logging
from typing import Optional

import boto3
from botocore.client import Config

from app.core.config import settings

logger = logging.getLogger(__name__)

_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=f"{'https' if settings.MINIO_USE_SSL else 'http'}://{settings.MINIO_ENDPOINT}",
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
    return _s3_client


def _ensure_bucket(bucket: str) -> None:
    s3 = get_s3_client()
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        s3.create_bucket(Bucket=bucket)
        logger.info(f"Created bucket: {bucket}")


async def get_presigned_upload(
    file_key: str,
    content_type: str,
    expires_seconds: int = 3600,
    bucket: Optional[str] = None,
) -> str:
    """Generate a presigned URL for direct upload to MinIO."""
    bucket = bucket or settings.MINIO_BUCKET_MEDIA
    _ensure_bucket(bucket)
    s3 = get_s3_client()
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": file_key, "ContentType": content_type},
        ExpiresIn=expires_seconds,
    )
    return url


async def get_presigned_download(
    file_key: str,
    expires_seconds: int = 900,
    bucket: Optional[str] = None,
) -> str:
    """Generate a presigned URL for downloading from MinIO."""
    bucket = bucket or settings.MINIO_BUCKET_MEDIA
    s3 = get_s3_client()
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": file_key},
        ExpiresIn=expires_seconds,
    )
    return url


async def delete_object(file_key: str, bucket: Optional[str] = None) -> None:
    bucket = bucket or settings.MINIO_BUCKET_MEDIA
    s3 = get_s3_client()
    s3.delete_object(Bucket=bucket, Key=file_key)
