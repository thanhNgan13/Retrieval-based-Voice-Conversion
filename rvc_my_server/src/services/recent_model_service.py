from typing import Optional

from src.models.recent_model_model import (
    get_rvc_model_snapshot,
    list_recent_models_paginated,
    upsert_recent_model,
)
from src.utils.cursor_pagination import normalize_limit
from src.utils.data_transform import convert_firestore_doc


class RvcModelNotFoundError(Exception):
    pass


def _format_recent_model(doc: dict) -> dict:
    snapshot = doc.get("snapshot") or {}
    result = convert_firestore_doc(snapshot)
    result["addedAt"] = doc.get("added_at", "")
    return result


def add_recent_model(user_id: str, rvc_model_id: str) -> dict:
    model_snapshot = get_rvc_model_snapshot(rvc_model_id)
    if model_snapshot is None:
        raise RvcModelNotFoundError(f"RVC model '{rvc_model_id}' not found")
    doc = upsert_recent_model(user_id, rvc_model_id, model_snapshot)
    return _format_recent_model(doc)


def list_recent_models(user_id: str, limit: Optional[int], start_after: Optional[str]) -> dict:
    n = normalize_limit(limit)
    items, has_next = list_recent_models_paginated(user_id, n, start_after)
    views = [_format_recent_model(d) for d in items]
    next_cursor = items[-1].get("rvc_model_id") if has_next and items else None
    return {
        "paginatedItems": views,
        "pagination": {
            "limit": n,
            "hasNext": has_next,
            "nextCursor": next_cursor,
            "currentCount": len(views),
        },
    }
