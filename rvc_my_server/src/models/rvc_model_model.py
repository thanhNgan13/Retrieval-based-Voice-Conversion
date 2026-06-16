from datetime import datetime, timezone
from typing import Optional, Tuple

from google.cloud.firestore_v1 import Query

from src.config.firebase import get_db
from src.utils.constant import RVC_MODELS_COLLECTION



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def prepare_rvc_model_data(
    rvc_model_id: str,
    title: str,
    description: str,
    thumbnail: str,
    model_path: str,
    index_path: str,
    storage_folder: str,
    created_by: str,
) -> dict:
    now = _now_iso()
    return {
        "rvc_model_id": rvc_model_id,
        "title": title.strip(),
        "description": (description or "").strip(),
        "thumbnail": thumbnail,
        "model_path": model_path,
        "index_path": index_path,
        "storage_folder": storage_folder,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }


def add_rvc_model_to_firestore(data: dict) -> None:
    db = get_db()
    db.collection(RVC_MODELS_COLLECTION).document(data["rvc_model_id"]).set(data)


def get_rvc_model_by_id(rvc_model_id: str) -> Optional[dict]:
    db = get_db()
    snap = db.collection(RVC_MODELS_COLLECTION).document(rvc_model_id).get()
    return snap.to_dict() if snap.exists else None


def update_rvc_model_in_firestore(rvc_model_id: str, updates: dict) -> Optional[dict]:
    db = get_db()
    ref = db.collection(RVC_MODELS_COLLECTION).document(rvc_model_id)
    snap = ref.get()
    if not snap.exists:
        return None
    payload = {**updates, "updated_at": _now_iso()}
    ref.update(payload)
    return ref.get().to_dict()


def delete_rvc_model_from_firestore(rvc_model_id: str) -> Optional[dict]:
    db = get_db()
    ref = db.collection(RVC_MODELS_COLLECTION).document(rvc_model_id)
    snap = ref.get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    ref.delete()
    return data


def list_rvc_models_paginated(
    limit: int,
    start_after: Optional[str],
    q: Optional[str] = None,
) -> Tuple[list, bool]:
    """
    Sort by created_at DESC. Fetches limit+1 to detect hasNext.
    When q is given, does prefix search on title ordered by title ASC.
    Returns (items_up_to_limit, has_next).
    """
    db = get_db()
    col = db.collection(RVC_MODELS_COLLECTION)

    if q:
        query = (
            col
            .order_by("title")
            .where("title", ">=", q)
            .where("title", "<=", q + "")
        )
    else:
        query = col.order_by("created_at", direction=Query.DESCENDING)

    if start_after:
        cursor_snap = col.document(start_after).get()
        if cursor_snap.exists:
            query = query.start_after(cursor_snap)

    query = query.limit(limit + 1)
    docs = [d.to_dict() for d in query.stream()]
    has_next = len(docs) > limit
    return docs[:limit], has_next


def delete_rvc_models_by_ids_from_firestore(
    rvc_model_ids: list[str],
) -> Tuple[list, list]:
    """Batch-delete docs by IDs. Returns (deleted_docs, not_found_ids)."""
    db = get_db()
    col = db.collection(RVC_MODELS_COLLECTION)

    deleted_docs: list = []
    not_found_ids: list = []
    to_delete_refs: list = []

    for mid in rvc_model_ids:
        snap = col.document(mid).get()
        if snap.exists:
            deleted_docs.append(snap.to_dict())
            to_delete_refs.append(snap.reference)
        else:
            not_found_ids.append(mid)

    batch = db.batch()
    i = 0
    for ref in to_delete_refs:
        batch.delete(ref)
        i += 1
        if i >= 500:
            batch.commit()
            batch = db.batch()
            i = 0
    if i > 0:
        batch.commit()

    return deleted_docs, not_found_ids


def delete_all_rvc_models_from_firestore() -> Tuple[int, list]:
    """Delete every rvc_models document. Returns (count, list_of_storage_folders)."""
    db = get_db()
    docs = list(db.collection(RVC_MODELS_COLLECTION).stream())
    folders = []
    for d in docs:
        data = d.to_dict() or {}
        folder = data.get("storage_folder")
        if folder:
            folders.append(folder)

    # Firestore batch hard-limit: 500 ops per commit.
    count = 0
    batch = db.batch()
    i = 0
    for d in docs:
        batch.delete(d.reference)
        count += 1
        i += 1
        if i >= 500:
            batch.commit()
            batch = db.batch()
            i = 0
    if i > 0:
        batch.commit()

    return count, folders
