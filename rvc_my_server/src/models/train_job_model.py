from datetime import datetime, timezone
from typing import Optional, Tuple

from google.cloud.firestore_v1 import Query

from src.config.firebase import get_db
from src.utils.constant import RVC_TRAIN_JOBS_COLLECTION


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def prepare_train_job_data(
    train_job_id: str,
    user_id: str,
    title: str,
    description: str,
    audio_object_paths: list[str],
    params: dict,
) -> dict:
    now = _now_iso()
    return {
        "train_job_id": train_job_id,
        "user_id": user_id,
        "title": title.strip(),
        "description": (description or "").strip(),
        "audio_object_paths": audio_object_paths,
        "audio_file_count": len(audio_object_paths),
        "params": params,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "message": "Training job queued",
        "rvc_model_id": "",
        "error": "",
        "created_at": now,
        "updated_at": now,
        "started_at": "",
        "completed_at": "",
    }


def add_train_job_to_firestore(data: dict) -> None:
    db = get_db()
    db.collection(RVC_TRAIN_JOBS_COLLECTION).document(data["train_job_id"]).set(data)


def get_train_job_by_id(train_job_id: str) -> Optional[dict]:
    db = get_db()
    snap = db.collection(RVC_TRAIN_JOBS_COLLECTION).document(train_job_id).get()
    return snap.to_dict() if snap.exists else None


def update_train_job_in_firestore(train_job_id: str, updates: dict) -> Optional[dict]:
    db = get_db()
    ref = db.collection(RVC_TRAIN_JOBS_COLLECTION).document(train_job_id)
    snap = ref.get()
    if not snap.exists:
        return None
    ref.update({**updates, "updated_at": _now_iso()})
    return ref.get().to_dict()


def list_user_train_jobs_paginated(
    user_id: str,
    limit: int,
    start_after: Optional[str],
) -> Tuple[list, bool]:
    db = get_db()
    query = (
        db.collection(RVC_TRAIN_JOBS_COLLECTION)
        .where("user_id", "==", user_id)
        .order_by("created_at", direction=Query.DESCENDING)
    )

    if start_after:
        cursor_snap = db.collection(RVC_TRAIN_JOBS_COLLECTION).document(start_after).get()
        if cursor_snap.exists:
            query = query.start_after(cursor_snap)

    docs = [d.to_dict() for d in query.limit(limit + 1).stream()]
    has_next = len(docs) > limit
    return docs[:limit], has_next
