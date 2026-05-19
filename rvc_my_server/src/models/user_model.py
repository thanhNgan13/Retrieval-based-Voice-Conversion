from datetime import datetime, timezone
from typing import Optional

from google.cloud.firestore_v1.base_query import FieldFilter

from src.config.firebase import get_db
from src.utils.constant import DEFAULT_ROLE, USERS_COLLECTION


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def prepare_user_data(
    user_id: str,
    email: str,
    name: str,
    password_hash: str,
    role: str = DEFAULT_ROLE,
) -> dict:
    now = _now_iso()
    return {
        "user_id": user_id,
        "email": email.lower(),
        "name": name.strip(),
        "password_hash": password_hash,
        "avatar_url": "",
        "role": role,
        "created_at": now,
        "updated_at": now,
    }


def add_user_to_firestore(user_data: dict) -> None:
    db = get_db()
    db.collection(USERS_COLLECTION).document(user_data["user_id"]).set(user_data)


def get_user_by_id(user_id: str) -> Optional[dict]:
    db = get_db()
    snap = db.collection(USERS_COLLECTION).document(user_id).get()
    return snap.to_dict() if snap.exists else None


def get_user_by_email(email: str) -> Optional[dict]:
    db = get_db()
    query = (
        db.collection(USERS_COLLECTION)
        .where(filter=FieldFilter("email", "==", email.lower()))
        .limit(1)
    )
    docs = list(query.stream())
    if not docs:
        return None
    return docs[0].to_dict()
