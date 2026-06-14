from datetime import datetime, timezone
from typing import Optional, Tuple

from google.cloud.firestore_v1 import Query

from src.config.firebase import get_db
from src.utils.constant import RVC_SONG_INFER_JOBS_COLLECTION


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def prepare_song_infer_job_data(
    song_infer_job_id: str,
    user_id: str,
    input_object_path: str,
    input_file_name: str,
    rvc_model_id: str,
    params: dict,
) -> dict:
    now = _now_iso()
    return {
        "song_infer_job_id": song_infer_job_id,
        "user_id": user_id,
        "input_object_path": input_object_path,
        "input_file_name": input_file_name,
        "rvc_model_id": rvc_model_id,
        "params": params,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "elapsed_ms": 0,
        "message": "Song inference job queued",
        "outputs": {},
        "error": "",
        "created_at": now,
        "updated_at": now,
        "started_at": "",
        "completed_at": "",
    }


def add_song_infer_job_to_firestore(data: dict) -> None:
    db = get_db()
    db.collection(RVC_SONG_INFER_JOBS_COLLECTION).document(data["song_infer_job_id"]).set(data)


def get_song_infer_job_by_id(song_infer_job_id: str) -> Optional[dict]:
    db = get_db()
    snap = db.collection(RVC_SONG_INFER_JOBS_COLLECTION).document(song_infer_job_id).get()
    return snap.to_dict() if snap.exists else None


def update_song_infer_job_in_firestore(song_infer_job_id: str, updates: dict) -> Optional[dict]:
    db = get_db()
    ref = db.collection(RVC_SONG_INFER_JOBS_COLLECTION).document(song_infer_job_id)
    snap = ref.get()
    if not snap.exists:
        return None
    ref.update({**updates, "updated_at": _now_iso()})
    return ref.get().to_dict()


def list_user_song_infer_jobs_paginated(
    user_id: str,
    limit: int,
    start_after: Optional[str],
) -> Tuple[list, bool]:
    db = get_db()
    query = (
        db.collection(RVC_SONG_INFER_JOBS_COLLECTION)
        .where("user_id", "==", user_id)
        .order_by("created_at", direction=Query.DESCENDING)
    )

    if start_after:
        cursor_snap = db.collection(RVC_SONG_INFER_JOBS_COLLECTION).document(start_after).get()
        if cursor_snap.exists:
            query = query.start_after(cursor_snap)

    docs = [d.to_dict() for d in query.limit(limit + 1).stream()]
    has_next = len(docs) > limit
    return docs[:limit], has_next
