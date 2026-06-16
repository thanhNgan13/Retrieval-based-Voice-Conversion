from datetime import datetime, timezone
from typing import Optional, Tuple

from google.cloud.firestore_v1 import Query

from src.config.firebase import get_db
from src.utils.constant import (
    RECENT_MODELS_SUBCOLLECTION,
    RVC_MODELS_COLLECTION,
    USERS_COLLECTION,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _recent_models_ref(db, user_id: str):
    return db.collection(USERS_COLLECTION).document(user_id).collection(RECENT_MODELS_SUBCOLLECTION)


def get_rvc_model_snapshot(rvc_model_id: str) -> Optional[dict]:
    db = get_db()
    snap = db.collection(RVC_MODELS_COLLECTION).document(rvc_model_id).get()
    return snap.to_dict() if snap.exists else None


def upsert_recent_model(user_id: str, rvc_model_id: str, model_snapshot: dict) -> dict:
    db = get_db()
    data = {
        "rvc_model_id": rvc_model_id,
        "user_id": user_id,
        "added_at": _now_iso(),
        "snapshot": model_snapshot,
    }
    _recent_models_ref(db, user_id).document(rvc_model_id).set(data)
    return data


def list_recent_models_paginated(
    user_id: str,
    limit: int,
    start_after: Optional[str],
) -> Tuple[list, bool]:
    db = get_db()
    ref = _recent_models_ref(db, user_id)
    query = ref.order_by("added_at", direction=Query.DESCENDING)

    if start_after:
        cursor_snap = ref.document(start_after).get()
        if cursor_snap.exists:
            query = query.start_after(cursor_snap)

    docs = [d.to_dict() for d in query.limit(limit + 1).stream()]
    has_next = len(docs) > limit
    return docs[:limit], has_next
