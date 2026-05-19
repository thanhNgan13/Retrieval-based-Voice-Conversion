from urllib.parse import quote


def firebase_download_url(bucket_name: str, object_path: str, token: str) -> str:
    """Build a public download URL that works with Uniform bucket-level access.

    The URL is recognized by Firebase Storage Rules — anyone with the token can read.
    """
    return (
        f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}"
        f"/o/{quote(object_path, safe='')}?alt=media&token={token}"
    )
