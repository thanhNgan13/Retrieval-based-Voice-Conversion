from typing import Optional

from src.models.list_cover_model import (
    add_cover_to_firestore,
    cover_exists,
    list_user_covers_paginated,
    prepare_cover_data,
)
from src.models.song_infer_job_model import list_all_succeeded_song_infer_jobs
from src.models.user_rvc_model_model import get_accessible_rvc_model_by_id
from src.utils.cursor_pagination import normalize_limit
from src.utils.data_transform import convert_firestore_doc

_MODEL_DROP_KEYS = ("model_path", "index_path", "storage_folder")


def _public_cover_view(doc: dict) -> dict:
    return convert_firestore_doc(doc)


def _cover_model_snapshot(model_doc: Optional[dict]) -> dict:
    if not model_doc:
        return {}
    return {k: v for k, v in model_doc.items() if k not in _MODEL_DROP_KEYS}


def save_completed_cover(job_doc: dict, outputs: dict, completed_at: str) -> dict:
    model_doc = get_accessible_rvc_model_by_id(
        job_doc["user_id"],
        job_doc.get("rvc_model_id", ""),
    )
    doc = prepare_cover_data(
        job_doc=job_doc,
        outputs=outputs,
        completed_at=completed_at,
        rvc_model=_cover_model_snapshot(model_doc),
    )
    add_cover_to_firestore(doc)
    return _public_cover_view(doc)


def backfill_covers_from_succeeded_jobs() -> dict:
    jobs = list_all_succeeded_song_infer_jobs()
    created = 0
    skipped = 0
    failed = 0
    for job_doc in jobs:
        cover_id = job_doc.get("song_infer_job_id", "")
        if not cover_id:
            skipped += 1
            continue
        if cover_exists(cover_id):
            skipped += 1
            continue
        outputs = job_doc.get("outputs") or {}
        if not outputs.get("mixing", {}).get("finalMix"):
            skipped += 1
            continue
        try:
            completed_at = job_doc.get("completed_at", "")
            save_completed_cover(job_doc, outputs, completed_at)
            created += 1
        except Exception:
            failed += 1
    return {"created": created, "skipped": skipped, "failed": failed, "total": len(jobs)}


def list_covers(user_id: str, limit: Optional[int], start_after: Optional[str]) -> dict:
    n = normalize_limit(limit)
    items, has_next = list_user_covers_paginated(user_id, n, start_after)
    views = [_public_cover_view(d) for d in items]
    next_cursor = items[-1].get("cover_id") if has_next and items else None
    return {
        "paginatedItems": views,
        "pagination": {
            "limit": n,
            "hasNext": has_next,
            "nextCursor": next_cursor,
            "currentCount": len(views),
        },
    }
