from datetime import datetime, timezone
from typing import Optional, Tuple

from google.cloud.firestore_v1 import Query

from src.config.firebase import get_db
from src.utils.constant import (
    RVC_MODELS_COLLECTION,
    USER_RVC_MODELS_SUBCOLLECTION,
    USERS_COLLECTION,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _user_models_ref(user_id: str):
    return (
        get_db()
        .collection(USERS_COLLECTION)
        .document(user_id)
        .collection(USER_RVC_MODELS_SUBCOLLECTION)
    )


def prepare_user_rvc_model_data(
    rvc_model_id: str,
    user_id: str,
    title: str,
    description: str,
    model_path: str,
    index_path: str,
    storage_folder: str,
    train_job_id: str,
    params: dict,
) -> dict:
    now = _now_iso()
    return {
        "rvc_model_id": rvc_model_id,
        "user_id": user_id,
        "title": title.strip(),
        "description": (description or "").strip(),
        "thumbnail": "",
        "model_path": model_path,
        "index_path": index_path,
        "storage_folder": storage_folder,
        "train_job_id": train_job_id,
        "params": params,
        "visibility": "private",
        "created_by": user_id,
        "created_at": now,
        "updated_at": now,
    }


def add_user_rvc_model_to_firestore(data: dict) -> None:
    _user_models_ref(data["user_id"]).document(data["rvc_model_id"]).set(data)


def get_user_rvc_model_by_id(user_id: str, rvc_model_id: str) -> Optional[dict]:
    snap = _user_models_ref(user_id).document(rvc_model_id).get()
    return snap.to_dict() if snap.exists else None


def get_accessible_rvc_model_by_id(user_id: str, rvc_model_id: str) -> Optional[dict]:
    private_doc = get_user_rvc_model_by_id(user_id, rvc_model_id)
    if private_doc:
        return private_doc

    snap = get_db().collection(RVC_MODELS_COLLECTION).document(rvc_model_id).get()
    return snap.to_dict() if snap.exists else None


def list_user_rvc_models_paginated(
    user_id: str,
    limit: int,
    start_after: Optional[str],
) -> Tuple[list, bool]:
    query = _user_models_ref(user_id).order_by(
        "created_at", direction=Query.DESCENDING
    )

    if start_after:
        cursor_snap = _user_models_ref(user_id).document(start_after).get()
        if cursor_snap.exists:
            query = query.start_after(cursor_snap)

    docs = [d.to_dict() for d in query.limit(limit + 1).stream()]
    has_next = len(docs) > limit
    return docs[:limit], has_next
