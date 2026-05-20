from urllib.parse import quote
from datetime import timedelta
from typing import Optional

from src.config.firebase import get_bucket
from src.config.settings import settings


def firebase_download_url(bucket_name: str, object_path: str, token: str) -> str:
    """Build a public download URL that works with Uniform bucket-level access.

    The URL is recognized by Firebase Storage Rules — anyone with the token can read.
    """
    return (
        f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}"
        f"/o/{quote(object_path, safe='')}?alt=media&token={token}"
    )


def generate_signed_upload_url(
    object_path: str,
    content_type: str,
    expires_seconds: Optional[int] = None,
) -> str:
    bucket = get_bucket()
    blob = bucket.blob(object_path)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(
            seconds=expires_seconds or settings.SIGNED_UPLOAD_URL_EXPIRES_SECONDS
        ),
        method="PUT",
        content_type=content_type,
    )


def generate_signed_download_url(
    object_path: str,
    expires_seconds: Optional[int] = None,
) -> str:
    bucket = get_bucket()
    blob = bucket.blob(object_path)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(
            seconds=expires_seconds or settings.SIGNED_DOWNLOAD_URL_EXPIRES_SECONDS
        ),
        method="GET",
    )
