import logging
import mimetypes
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from src.config.firebase import get_bucket
from src.config.settings import settings
from src.models.my_song_model import (
    add_my_song_to_firestore,
    delete_my_song_from_firestore,
    get_my_song_by_id,
    list_my_songs_paginated,
    prepare_my_song_data,
    update_my_song_in_firestore,
)
from src.models.user_model import get_user_by_id
from src.schemas.my_song_schema import CreateMySongUploadUrlRequest, UpdateMySongRequest
from src.utils.constant import USER_SONGS_FOLDER
from src.utils.cursor_pagination import build_pagination_block, normalize_limit
from src.utils.id_generator import generate_my_song_id
from src.utils.storage_helpers import generate_signed_download_url, generate_signed_upload_url

logger = logging.getLogger(__name__)

VALID_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma"}


class MySongNotFoundError(Exception):
    pass


class InvalidMySongRequestError(Exception):
    pass


def _safe_filename(name: str) -> str:
    stem = Path(name or "audio.mp3").stem
    ext = Path(name or "audio.mp3").suffix.lower() or ".mp3"
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("._-") or "audio"
    return "%s%s" % (stem[:80], ext)


def _assert_audio_file(name: str, content_type: str) -> None:
    ext = Path(name).suffix.lower()
    if ext not in VALID_AUDIO_EXTS:
        raise InvalidMySongRequestError(
            "audio file extension must be one of %s" % sorted(VALID_AUDIO_EXTS)
        )
    if content_type and not content_type.startswith("audio/"):
        guessed, _ = mimetypes.guess_type(name)
        if not guessed or not guessed.startswith("audio/"):
            raise InvalidMySongRequestError("contentType must be an audio/* type")


def _get_user_display_name(user_id: str) -> str:
    user = get_user_by_id(user_id) or {}
    return (
        str(user.get("name") or user.get("display_name") or user.get("email") or user_id)
        .strip()
        or user_id
    )


def _normalize_artists(artists: Optional[list[str]], default_name: str) -> list[str]:
    cleaned = [str(item).strip() for item in (artists or []) if str(item).strip()]
    return cleaned or [default_name]


def _default_cover_image_url(title: str) -> str:
    params = urlencode(
        {
            "name": title or "Song",
            "background": "0D8ABC",
            "color": "fff",
            "size": "512",
            "bold": "true",
            "format": "png",
        }
    )
    return f"https://ui-avatars.com/api/?{params}"


def _song_view(doc: dict) -> dict:
    view = {
        "id": doc.get("id") or doc.get("song_id", ""),
        "artists": doc.get("artists") or [],
        "audioUrl": "",
        "duration": doc.get("duration", ""),
        "uploader": doc.get("uploader", ""),
        "coverImage": doc.get("cover_image") or _default_cover_image_url(doc.get("title", "")),
        "title": doc.get("title", ""),
        "createdAt": doc.get("created_at", ""),
        "playlistId": doc.get("playlist_id", ""),
    }
    if doc.get("object_path") and doc.get("status") == "uploaded":
        view["audioUrl"] = generate_signed_download_url(doc["object_path"])
    return view


def create_my_song_upload_url(body: CreateMySongUploadUrlRequest, user_id: str) -> dict:
    _assert_audio_file(body.file_name, body.content_type)

    song_id = generate_my_song_id()
    safe_name = _safe_filename(body.file_name)
    object_path = f"{USER_SONGS_FOLDER}/{user_id}/{song_id}_{safe_name}"

    upload_url = generate_signed_upload_url(object_path, body.content_type)
    user_display_name = _get_user_display_name(user_id)

    data = prepare_my_song_data(
        song_id=song_id,
        user_id=user_id,
        title=body.title,
        description=body.description,
        file_name=body.file_name,
        object_path=object_path,
        content_type=body.content_type,
        artists=_normalize_artists(body.artists, user_display_name),
        duration=body.duration,
        uploader=user_display_name,
        cover_image=_default_cover_image_url(body.title),
    )
    add_my_song_to_firestore(data)

    return {
        "id": song_id,
        "songId": song_id,
        "objectPath": object_path,
        "song": _song_view(data),
        "uploadUrl": upload_url,
        "method": "PUT",
        "headers": {"Content-Type": body.content_type},
        "expiresIn": settings.SIGNED_UPLOAD_URL_EXPIRES_SECONDS,
    }


def confirm_my_song_upload(user_id: str, song_id: str) -> dict:
    doc = get_my_song_by_id(user_id, song_id)
    if doc is None:
        raise MySongNotFoundError("Song %s not found" % song_id)
    if doc.get("user_id") != user_id:
        raise MySongNotFoundError("Song %s not found" % song_id)

    bucket = get_bucket()
    blob = bucket.blob(doc["object_path"])
    if not blob.exists():
        raise InvalidMySongRequestError(
            "Audio file has not been uploaded yet. Please PUT the file to the signed URL first."
        )

    updated = update_my_song_in_firestore(user_id, song_id, {"status": "uploaded"})
    return _song_view(updated)


def get_my_song_detail(user_id: str, song_id: str) -> dict:
    doc = get_my_song_by_id(user_id, song_id)
    if doc is None or doc.get("user_id") != user_id:
        raise MySongNotFoundError("Song %s not found" % song_id)
    return _song_view(doc)


def list_my_songs(user_id: str, limit: Optional[int], start_after: Optional[str]) -> dict:
    norm_limit = normalize_limit(limit)
    docs = list_my_songs_paginated(user_id, norm_limit, start_after)
    items = [_song_view(doc) for doc in docs]
    pagination = build_pagination_block(items, norm_limit, id_field="id")
    return {
        "paginatedItems": items[: norm_limit],
        "pagination": pagination,
    }


def update_my_song(user_id: str, song_id: str, body: UpdateMySongRequest) -> dict:
    doc = get_my_song_by_id(user_id, song_id)
    if doc is None or doc.get("user_id") != user_id:
        raise MySongNotFoundError("Song %s not found" % song_id)

    updates = {}
    if body.title is not None:
        updates["title"] = body.title
    if body.description is not None:
        updates["description"] = body.description
    if body.artists is not None:
        updates["artists"] = _normalize_artists(
            body.artists,
            doc.get("uploader") or _get_user_display_name(user_id),
        )
    if body.duration is not None:
        updates["duration"] = body.duration
    if body.cover_image is not None:
        updates["cover_image"] = body.cover_image or _default_cover_image_url(
            body.title or doc.get("title", "")
        )

    if not updates:
        return _song_view(doc)

    updated = update_my_song_in_firestore(user_id, song_id, updates)
    return _song_view(updated)


def delete_my_song(user_id: str, song_id: str) -> dict:
    doc = get_my_song_by_id(user_id, song_id)
    if doc is None or doc.get("user_id") != user_id:
        raise MySongNotFoundError("Song %s not found" % song_id)

    object_path = doc.get("object_path", "")
    if object_path:
        try:
            bucket = get_bucket()
            blob = bucket.blob(object_path)
            if blob.exists():
                blob.delete()
        except Exception:
            logger.warning("Failed to delete storage object %s", object_path)

    delete_my_song_from_firestore(user_id, song_id)
    return _song_view(doc)
