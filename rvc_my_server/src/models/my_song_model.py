from datetime import datetime, timezone
from typing import Optional

from src.config.firebase import get_db
from src.utils.constant import USERS_COLLECTION, MY_SONGS_SUBCOLLECTION


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _col(user_id: str):
    db = get_db()
    return db.collection(USERS_COLLECTION).document(user_id).collection(MY_SONGS_SUBCOLLECTION)


def prepare_my_song_data(
    song_id: str,
    user_id: str,
    title: str,
    description: str,
    file_name: str,
    object_path: str,
    content_type: str,
    artists: list[str],
    duration: str,
    uploader: str,
    cover_image: str,
) -> dict:
    now = _now_iso()
    return {
        "id": song_id,
        "song_id": song_id,
        "user_id": user_id,
        "playlist_id": "",
        "title": title,
        "description": description,
        "artists": artists,
        "duration": duration,
        "uploader": uploader,
        "cover_image": cover_image,
        "file_name": file_name,
        "object_path": object_path,
        "content_type": content_type,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    }


def add_my_song_to_firestore(data: dict) -> None:
    _col(data["user_id"]).document(data["song_id"]).set(data)


def get_my_song_by_id(user_id: str, song_id: str) -> Optional[dict]:
    snap = _col(user_id).document(song_id).get()
    return snap.to_dict() if snap.exists else None


def update_my_song_in_firestore(user_id: str, song_id: str, updates: dict) -> Optional[dict]:
    ref = _col(user_id).document(song_id)
    snap = ref.get()
    if not snap.exists:
        return None
    ref.update({**updates, "updated_at": _now_iso()})
    return ref.get().to_dict()


def delete_my_song_from_firestore(user_id: str, song_id: str) -> Optional[dict]:
    ref = _col(user_id).document(song_id)
    snap = ref.get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    ref.delete()
    return data


def list_my_songs_paginated(
    user_id: str,
    limit: int,
    start_after: Optional[str] = None,
) -> list[dict]:
    query = _col(user_id).order_by("created_at", direction="DESCENDING")
    if start_after:
        cursor_snap = _col(user_id).document(start_after).get()
        if cursor_snap.exists:
            query = query.start_after(cursor_snap)
    docs = query.limit(limit + 1).stream()
    return [doc.to_dict() for doc in docs]
