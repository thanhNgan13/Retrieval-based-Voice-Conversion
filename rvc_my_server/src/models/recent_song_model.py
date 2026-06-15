from datetime import datetime, timezone
from typing import Optional, Tuple

from google.cloud.firestore_v1 import Query

from src.config.firebase import get_db
from src.utils.constant import (
    PLAYLISTS_COLLECTION,
    RECENT_SONGS_SUBCOLLECTION,
    SONGS_SUBCOLLECTION,
    USERS_COLLECTION,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _recent_songs_ref(db, user_id: str):
    return db.collection(USERS_COLLECTION).document(user_id).collection(RECENT_SONGS_SUBCOLLECTION)


def get_song_snapshot(playlist_id: str, song_id: str) -> Optional[dict]:
    db = get_db()
    snap = (
        db.collection(PLAYLISTS_COLLECTION)
        .document(playlist_id)
        .collection(SONGS_SUBCOLLECTION)
        .document(song_id)
        .get()
    )
    return snap.to_dict() if snap.exists else None


def upsert_recent_song(user_id: str, song_id: str, playlist_id: str, song_snapshot: dict) -> dict:
    db = get_db()
    data = {
        "song_id": song_id,
        "playlist_id": playlist_id,
        "user_id": user_id,
        "added_at": _now_iso(),
        "snapshot": song_snapshot,
    }
    _recent_songs_ref(db, user_id).document(song_id).set(data)
    return data


def list_recent_songs_paginated(
    user_id: str,
    limit: int,
    start_after: Optional[str],
) -> Tuple[list, bool]:
    db = get_db()
    ref = _recent_songs_ref(db, user_id)
    query = ref.order_by("added_at", direction=Query.DESCENDING)

    if start_after:
        cursor_snap = ref.document(start_after).get()
        if cursor_snap.exists:
            query = query.start_after(cursor_snap)

    docs = [d.to_dict() for d in query.limit(limit + 1).stream()]
    has_next = len(docs) > limit
    return docs[:limit], has_next
