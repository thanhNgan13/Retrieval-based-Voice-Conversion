from datetime import datetime, timezone
from typing import Optional, Tuple

from google.cloud.firestore_v1 import Query

from src.config.firebase import get_db
from src.utils.constant import LIST_COVER_COLLECTION


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def prepare_cover_data(
    job_doc: dict,
    outputs: dict,
    completed_at: str,
    rvc_model: Optional[dict] = None,
) -> dict:
    now = _now_iso()
    song_infer_job_id = job_doc["song_infer_job_id"]
    mixing_outputs = outputs.get("mixing") or {}
    infer_outputs = outputs.get("infer") or {}
    return {
        "cover_id": song_infer_job_id,
        "user_id": job_doc["user_id"],
        "song_infer_job_id": song_infer_job_id,
        "source_song": {
            "file_name": job_doc.get("input_file_name", ""),
            "input_object_path": job_doc.get("input_object_path", ""),
            "source_song_id": job_doc.get("source_song_id", ""),
            "song_info": job_doc.get("song_info") or {},
        },
        "rvc_model_id": job_doc.get("rvc_model_id", ""),
        "rvc_model": rvc_model or {},
        "params": job_doc.get("params") or {},
        "outputs": outputs,
        "final_mix": mixing_outputs.get("finalMix", {}),
        "ai_vocals_wet": mixing_outputs.get("aiVocalsWet", {}),
        "converted_main_vocals": infer_outputs.get("convertedMainVocals", {}),
        "separation": outputs.get("separation") or {},
        "audio_info": mixing_outputs.get("audioInfo", {}),
        "created_at": completed_at or now,
        "updated_at": now,
        "completed_at": completed_at,
    }


def cover_exists(cover_id: str) -> bool:
    db = get_db()
    return db.collection(LIST_COVER_COLLECTION).document(cover_id).get().exists


def add_cover_to_firestore(data: dict) -> None:
    db = get_db()
    db.collection(LIST_COVER_COLLECTION).document(data["cover_id"]).set(data)


def list_user_covers_paginated(
    user_id: str,
    limit: int,
    start_after: Optional[str],
) -> Tuple[list, bool]:
    db = get_db()
    query = (
        db.collection(LIST_COVER_COLLECTION)
        .where("user_id", "==", user_id)
        .order_by("created_at", direction=Query.DESCENDING)
    )

    if start_after:
        cursor_snap = db.collection(LIST_COVER_COLLECTION).document(start_after).get()
        if cursor_snap.exists:
            query = query.start_after(cursor_snap)

    docs = [d.to_dict() for d in query.limit(limit + 1).stream()]
    has_next = len(docs) > limit
    return docs[:limit], has_next
