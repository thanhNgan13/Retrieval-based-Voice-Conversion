from typing import Optional

from src.models.recent_song_model import list_recent_songs_paginated, upsert_recent_song
from src.utils.cursor_pagination import normalize_limit
from src.utils.data_transform import convert_firestore_doc


def add_recent_song(user_id: str, song_id: str) -> dict:
    doc = upsert_recent_song(user_id, song_id)
    return convert_firestore_doc(doc)


def list_recent_songs(user_id: str, limit: Optional[int], start_after: Optional[str]) -> dict:
    n = normalize_limit(limit)
    items, has_next = list_recent_songs_paginated(user_id, n, start_after)
    views = [convert_firestore_doc(d) for d in items]
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
