from typing import Optional

from src.models.recent_song_model import (
    get_song_snapshot,
    list_recent_songs_paginated,
    upsert_recent_song,
)
from src.utils.cursor_pagination import normalize_limit
from src.utils.data_transform import convert_firestore_doc


class SongNotFoundError(Exception):
    pass


def _format_recent_song(doc: dict) -> dict:
    snapshot = doc.get("snapshot") or {}
    result = convert_firestore_doc(snapshot)
    result["addedAt"] = doc.get("added_at", "")
    return result


def add_recent_song(user_id: str, song_id: str, playlist_id: str) -> dict:
    song_snapshot = get_song_snapshot(playlist_id, song_id)
    if song_snapshot is None:
        raise SongNotFoundError(f"Song '{song_id}' not found in playlist '{playlist_id}'")
    doc = upsert_recent_song(user_id, song_id, playlist_id, song_snapshot)
    return _format_recent_song(doc)


def list_recent_songs(user_id: str, limit: Optional[int], start_after: Optional[str]) -> dict:
    n = normalize_limit(limit)
    items, has_next = list_recent_songs_paginated(user_id, n, start_after)
    views = [_format_recent_song(d) for d in items]
    next_cursor = items[-1].get("song_id") if has_next and items else None
    return {
        "paginatedItems": views,
        "pagination": {
            "limit": n,
            "hasNext": has_next,
            "nextCursor": next_cursor,
            "currentCount": len(views),
        },
    }
