import logging
import uuid as uuid_lib
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import UploadFile

from src.config.firebase import get_bucket
from src.models.rvc_model_model import (
    add_rvc_model_to_firestore,
    delete_all_rvc_models_from_firestore,
    delete_rvc_model_from_firestore,
    delete_rvc_models_by_ids_from_firestore,
    get_rvc_model_by_id,
    list_rvc_models_paginated,
    prepare_rvc_model_data,
    update_rvc_model_in_firestore,
)
from src.utils.constant import PUBLIC_RVC_MODEL_FOLDER
from src.utils.cursor_pagination import normalize_limit
from src.utils.data_transform import convert_firestore_doc
from src.utils.id_generator import generate_rvc_model_id
from src.utils.slugify import slugify

logger = logging.getLogger(__name__)


VALID_THUMBNAIL_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_INTERNAL_DROP_KEYS = ("storage_folder",)


class RvcModelNotFoundError(Exception):
    pass


class InvalidUploadError(Exception):
    pass


def _public_view(doc: dict) -> dict:
    return convert_firestore_doc(doc, drop_keys=_INTERNAL_DROP_KEYS)


def _assert_extension(file: UploadFile, expected_ext: str, field_name: str) -> None:
    name = (file.filename or "").lower()
    if not name.endswith(expected_ext):
        raise InvalidUploadError(
            f"{field_name} must have extension '{expected_ext}' (got '{file.filename}')"
        )


def _firebase_download_url(bucket_name: str, object_path: str, token: str) -> str:
    # Standard Firebase Storage download URL, works with Uniform bucket-level access.
    return (
        f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}"
        f"/o/{quote(object_path, safe='')}?alt=media&token={token}"
    )


def _upload_to_storage(
    file: UploadFile,
    dest_path: str,
    make_public: bool = False,
) -> Optional[str]:
    bucket = get_bucket()
    blob = bucket.blob(dest_path)
    file.file.seek(0)

    if make_public:
        token = str(uuid_lib.uuid4())
        blob.metadata = {"firebaseStorageDownloadTokens": token}
        blob.upload_from_file(file.file, content_type=file.content_type)
        return _firebase_download_url(bucket.name, dest_path, token)

    blob.upload_from_file(file.file, content_type=file.content_type)
    return None


def _delete_storage_folder(folder_relative: str) -> None:
    """Delete every blob under public_rvc_model/{folder_relative}/."""
    if not folder_relative:
        return
    prefix = f"{PUBLIC_RVC_MODEL_FOLDER}/{folder_relative}/"
    bucket = get_bucket()
    blobs = list(bucket.list_blobs(prefix=prefix))
    for b in blobs:
        try:
            b.delete()
        except Exception:
            logger.warning("Failed to delete blob %s", b.name, exc_info=True)


def upload_rvc_model(
    title: str,
    description: str,
    model_file: UploadFile,
    index_file: UploadFile,
    thumbnail_file: Optional[UploadFile],
    created_by: str,
) -> dict:
    if not title or not title.strip():
        raise InvalidUploadError("title is required")
    _assert_extension(model_file, ".pth", "modelFile")
    _assert_extension(index_file, ".index", "indexFile")

    # Validate thumbnail extension BEFORE any upload so we don't have to rollback later.
    thumbnail_ext = ""
    if thumbnail_file is not None and thumbnail_file.filename:
        thumbnail_ext = Path(thumbnail_file.filename).suffix.lower()
        if thumbnail_ext not in VALID_THUMBNAIL_EXTS:
            raise InvalidUploadError(
                f"thumbnail extension must be one of {sorted(VALID_THUMBNAIL_EXTS)}"
            )

    rvc_model_id = generate_rvc_model_id()
    folder = f"{rvc_model_id}_{slugify(title)}"
    folder_path = f"{PUBLIC_RVC_MODEL_FOLDER}/{folder}"

    model_path = f"{folder_path}/model.pth"
    index_path = f"{folder_path}/model.index"

    try:
        _upload_to_storage(model_file, model_path)
        _upload_to_storage(index_file, index_path)

        thumbnail_url = ""
        if thumbnail_file is not None and thumbnail_file.filename:
            thumbnail_path = f"{folder_path}/thumbnail{thumbnail_ext}"
            thumbnail_url = (
                _upload_to_storage(thumbnail_file, thumbnail_path, make_public=True) or ""
            )

        doc = prepare_rvc_model_data(
            rvc_model_id=rvc_model_id,
            title=title,
            description=description,
            thumbnail=thumbnail_url,
            model_path=model_path,
            index_path=index_path,
            storage_folder=folder,
            created_by=created_by,
        )
        add_rvc_model_to_firestore(doc)
        return _public_view(doc)
    except Exception:
        # Best-effort rollback so a failed upload does not leave orphan blobs.
        _delete_storage_folder(folder)
        raise


def list_rvc_models(limit: Optional[int], start_after: Optional[str], q: Optional[str] = None) -> dict:
    n = normalize_limit(limit)
    items, has_next = list_rvc_models_paginated(n, start_after, q=q)

    paginated_items = [_public_view(d) for d in items]
    next_cursor = items[-1].get("rvc_model_id") if has_next and items else None

    return {
        "paginatedItems": paginated_items,
        "pagination": {
            "limit": n,
            "hasNext": has_next,
            "nextCursor": next_cursor,
            "currentCount": len(paginated_items),
        },
    }


def get_rvc_model_detail(rvc_model_id: str) -> dict:
    doc = get_rvc_model_by_id(rvc_model_id)
    if not doc:
        raise RvcModelNotFoundError("RVC model not found")
    return _public_view(doc)


def update_rvc_model(
    rvc_model_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    updates: dict = {}
    if title is not None:
        updates["title"] = title.strip()
    if description is not None:
        updates["description"] = description.strip()

    if not updates:
        existing = get_rvc_model_by_id(rvc_model_id)
        if not existing:
            raise RvcModelNotFoundError("RVC model not found")
        return _public_view(existing)

    updated = update_rvc_model_in_firestore(rvc_model_id, updates)
    if updated is None:
        raise RvcModelNotFoundError("RVC model not found")
    return _public_view(updated)


def delete_rvc_models_by_ids(rvc_model_ids: list[str]) -> dict:
    deleted_docs, not_found_ids = delete_rvc_models_by_ids_from_firestore(rvc_model_ids)
    for doc in deleted_docs:
        _delete_storage_folder(doc.get("storage_folder", ""))
    return {
        "deletedCount": len(deleted_docs),
        "deletedIds": [d["rvc_model_id"] for d in deleted_docs],
        "notFoundIds": not_found_ids,
    }


def delete_rvc_model(rvc_model_id: str) -> None:
    doc = delete_rvc_model_from_firestore(rvc_model_id)
    if doc is None:
        raise RvcModelNotFoundError("RVC model not found")
    _delete_storage_folder(doc.get("storage_folder", ""))


def delete_all_rvc_models() -> int:
    count, folders = delete_all_rvc_models_from_firestore()
    for f in folders:
        _delete_storage_folder(f)
    return count
