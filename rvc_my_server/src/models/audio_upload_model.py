from datetime import datetime, timezone
from typing import Optional

from src.config.firebase import get_db
from src.utils.constant import RVC_AUDIO_UPLOADS_COLLECTION


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def prepare_audio_upload_data(
    audio_upload_id: str,
    user_id: str,
    upload_session_id: str,
    file_name: str,
    object_path: str,
    content_type: str,
) -> dict:
    now = _now_iso()
    return {
        "audio_upload_id": audio_upload_id,
        "user_id": user_id,
        "upload_session_id": upload_session_id,
        "file_name": file_name,
        "object_path": object_path,
        "content_type": content_type,
        "status": "signed",
        "created_at": now,
        "updated_at": now,
    }


def add_audio_upload_to_firestore(data: dict) -> None:
    db = get_db()
    db.collection(RVC_AUDIO_UPLOADS_COLLECTION).document(data["audio_upload_id"]).set(data)


def get_audio_upload_by_id(audio_upload_id: str) -> Optional[dict]:
    db = get_db()
    snap = db.collection(RVC_AUDIO_UPLOADS_COLLECTION).document(audio_upload_id).get()
    return snap.to_dict() if snap.exists else None


def update_audio_upload_in_firestore(
    audio_upload_id: str,
    updates: dict,
) -> Optional[dict]:
    db = get_db()
    ref = db.collection(RVC_AUDIO_UPLOADS_COLLECTION).document(audio_upload_id)
    snap = ref.get()
    if not snap.exists:
        return None
    ref.update({**updates, "updated_at": _now_iso()})
    return ref.get().to_dict()


def list_audio_uploads_by_user(user_id: str) -> list[dict]:
    db = get_db()
    docs = (
        db.collection(RVC_AUDIO_UPLOADS_COLLECTION)
        .where("user_id", "==", user_id)
        .stream()
    )
    items = [doc.to_dict() for doc in docs]
    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items


def delete_audio_upload_from_firestore(audio_upload_id: str) -> Optional[dict]:
    db = get_db()
    ref = db.collection(RVC_AUDIO_UPLOADS_COLLECTION).document(audio_upload_id)
    snap = ref.get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    ref.delete()
    return data


def delete_audio_uploads_by_user(user_id: str) -> list[dict]:
    db = get_db()
    docs = list(
        db.collection(RVC_AUDIO_UPLOADS_COLLECTION)
        .where("user_id", "==", user_id)
        .stream()
    )
    deleted = []
    batch = db.batch()
    count = 0
    for doc in docs:
        deleted.append(doc.to_dict())
        batch.delete(doc.reference)
        count += 1
        if count >= 500:
            batch.commit()
            batch = db.batch()
            count = 0
    if count:
        batch.commit()
    return deleted
