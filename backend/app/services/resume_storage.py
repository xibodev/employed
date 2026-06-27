"""Durable, S3-compatible object storage for rendered resume PDF artifacts (R14).

In production the backend is Cloudflare R2 (S3-compatible), so resume PDFs
survive EC2 instance restarts instead of living on ephemeral local disk. The
client is built purely from settings and also works against AWS S3, MinIO, or
LocalStack. When storage is not configured the caller falls back to local disk
(dev/test/CI), so this module is import-safe even without ``boto3``.

Secret values (access key id / secret) are seeded out-of-band as SSM
SecureStrings and referenced by name at runtime — never stored in the repo.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """True when R2/S3 resume storage is fully configured and selected."""
    backend = (settings.resume_storage_backend or "local").strip().lower()
    if backend not in {"r2", "s3"}:
        return False
    return bool(
        settings.resume_s3_bucket
        and settings.resume_s3_endpoint_url
        and settings.resume_s3_access_key_id
        and settings.resume_s3_secret_access_key
    )


def make_client():
    """Return a configured boto3 S3 client for the resume bucket.

    Uses path-style addressing + SigV4, which Cloudflare R2 (and MinIO) require.
    """
    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except ImportError as exc:  # pragma: no cover - exercised only without boto3
        raise RuntimeError("boto3 is required for R2/S3 resume storage") from exc

    return boto3.client(
        "s3",
        endpoint_url=settings.resume_s3_endpoint_url,
        aws_access_key_id=settings.resume_s3_access_key_id,
        aws_secret_access_key=settings.resume_s3_secret_access_key,
        region_name=settings.resume_s3_region or "auto",
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def object_key(profile_version_id: str, filename: str) -> str:
    """Stable, collision-free key for a resume artifact."""
    return f"resumes/{profile_version_id}/{filename}"


def upload_pdf(pdf_bytes: bytes, *, key: str, content_type: str = "application/pdf") -> dict[str, Any]:
    """Upload ``pdf_bytes`` to the configured bucket under ``key``.

    Returns a JSON-serialisable reference ``{storage, bucket, key}`` so it can
    travel back through the arq result backend and be served later (e.g. via a
    presigned URL) by a download endpoint.
    """
    client = make_client()
    client.put_object(
        Bucket=settings.resume_s3_bucket,
        Key=key,
        Body=pdf_bytes,
        ContentType=content_type,
    )
    logger.info(
        "resume_storage.uploaded bucket=%s key=%s size_bytes=%s",
        settings.resume_s3_bucket,
        key,
        len(pdf_bytes),
    )
    return {"storage": "r2", "bucket": settings.resume_s3_bucket, "key": key}


def presigned_url(key: str, *, expires_in: int = 3600) -> str:
    """Return a time-limited GET URL for a stored artifact (for download endpoints)."""
    client = make_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.resume_s3_bucket, "Key": key},
        ExpiresIn=expires_in,
    )
