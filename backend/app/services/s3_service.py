"""
backend/app/services/s3_service.py

AWS S3 service for MediAssist AI — handles all file storage:
  - Medical image uploads (X-rays, body photos, prescriptions)
  - Presigned URL generation for direct frontend uploads
  - File downloads and deletions

Bucket name is read from settings.S3_BUCKET_NAME.
All S3 keys use the prefix pattern: uploads/{uuid4}-{filename}
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

# ── S3 client (created once per Lambda instance) ─────────────────────────────

def _get_client():
    """Return a boto3 S3 client. Uses Lambda IAM role in production."""
    kwargs = {"region_name": settings.AWS_REGION}
    # If explicit credentials are set (local dev / CI), use them
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client("s3", **kwargs)


_s3 = None


def _client():
    """Lazy-initialized singleton S3 client."""
    global _s3
    if _s3 is None:
        _s3 = _get_client()
    return _s3


# ── Public API ────────────────────────────────────────────────────────────────

def upload_file(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    prefix: str = "uploads",
) -> str:
    """
    Upload *file_bytes* to S3 and return the S3 key.

    Args:
        file_bytes:   Raw file content.
        filename:     Original filename (used for extension + readability).
        content_type: MIME type (e.g. "image/jpeg").
        prefix:       S3 path prefix (default "uploads").

    Returns:
        S3 key string, e.g. "uploads/550e8400-…-xray.jpg"

    Raises:
        RuntimeError on S3 failure.
    """
    s3_key = f"{prefix}/{uuid.uuid4()}-{filename}"
    bucket = settings.S3_BUCKET_NAME

    logger.info("Uploading %d bytes to s3://%s/%s", len(file_bytes), bucket, s3_key)
    try:
        _client().put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=file_bytes,
            ContentType=content_type,
        )
        logger.info("Upload successful: %s", s3_key)
        return s3_key
    except ClientError as exc:
        logger.error("S3 upload failed: %s", exc)
        raise RuntimeError(f"S3 upload failed: {exc}") from exc


def download_file(s3_key: str) -> bytes:
    """
    Download a file from S3 and return its raw bytes.

    Args:
        s3_key: The S3 object key (as returned by :func:`upload_file`).

    Returns:
        Raw file content as bytes.

    Raises:
        FileNotFoundError if the key does not exist.
        RuntimeError on other S3 failures.
    """
    bucket = settings.S3_BUCKET_NAME
    logger.info("Downloading s3://%s/%s", bucket, s3_key)
    try:
        response = _client().get_object(Bucket=bucket, Key=s3_key)
        data = response["Body"].read()
        logger.info("Downloaded %d bytes from %s", len(data), s3_key)
        return data
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code in ("NoSuchKey", "404"):
            raise FileNotFoundError(f"S3 key not found: {s3_key}") from exc
        logger.error("S3 download failed: %s", exc)
        raise RuntimeError(f"S3 download failed: {exc}") from exc


def generate_presigned_url(
    s3_key: str,
    expiry_seconds: int = 3600,
    http_method: str = "get_object",
) -> str:
    """
    Generate a presigned URL for direct frontend access.

    Default is a GET URL (for viewing/downloading). Pass
    ``http_method="put_object"`` to generate an upload URL.

    Args:
        s3_key:         The S3 object key.
        expiry_seconds: URL expiry in seconds (default 1 hour).
        http_method:    Boto3 method name ("get_object" or "put_object").

    Returns:
        Presigned URL string.
    """
    bucket = settings.S3_BUCKET_NAME
    logger.info(
        "Generating presigned URL for s3://%s/%s (expires %ds)",
        bucket,
        s3_key,
        expiry_seconds,
    )
    try:
        url = _client().generate_presigned_url(
            ClientMethod=http_method,
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=expiry_seconds,
        )
        return url
    except ClientError as exc:
        logger.error("Failed to generate presigned URL: %s", exc)
        raise RuntimeError(f"Presigned URL generation failed: {exc}") from exc


def delete_file(s3_key: str) -> bool:
    """
    Delete a file from S3.

    Returns:
        True on success, False if the key did not exist.

    Raises:
        RuntimeError on unexpected S3 failures.
    """
    bucket = settings.S3_BUCKET_NAME
    logger.info("Deleting s3://%s/%s", bucket, s3_key)
    try:
        _client().delete_object(Bucket=bucket, Key=s3_key)
        logger.info("Deleted %s", s3_key)
        return True
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code in ("NoSuchKey", "404"):
            logger.warning("Tried to delete non-existent key: %s", s3_key)
            return False
        logger.error("S3 delete failed: %s", exc)
        raise RuntimeError(f"S3 delete failed: {exc}") from exc


def file_exists(s3_key: str) -> bool:
    """Return True if *s3_key* exists in the configured bucket."""
    bucket = settings.S3_BUCKET_NAME
    try:
        _client().head_object(Bucket=bucket, Key=s3_key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise
