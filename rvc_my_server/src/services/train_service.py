import logging
import mimetypes
import re
import shutil
import time
from pathlib import Path
from typing import Optional

from src.config.firebase import get_bucket
from src.config.settings import settings
from src.models.audio_upload_model import (
    add_audio_upload_to_firestore,
    delete_audio_upload_from_firestore,
    delete_audio_uploads_by_user,
    get_audio_upload_by_id,
    list_audio_uploads_by_user,
    prepare_audio_upload_data,
    update_audio_upload_in_firestore,
)
from src.models.train_job_model import (
    add_train_job_to_firestore,
    get_train_job_by_id,
    list_user_train_jobs_paginated,
    prepare_train_job_data,
)
from src.models.user_rvc_model_model import (
    add_user_rvc_model_to_firestore,
    get_user_rvc_model_by_id,
    list_user_rvc_models_paginated,
    prepare_user_rvc_model_data,
)
from src.schemas.train_schema import CreateTrainJobRequest, CreateTrainUploadUrlsRequest
# NOTE: rvc_train_pipeline is imported lazily inside execute_train_job because
# it pulls numpy + sklearn + RVC ML stack at module top — the api-light image
# does NOT install those (only the GPU image / worker does).
from src.services.train_progress import publish_train_progress
from src.utils.constant import PRIVATE_RVC_MODEL_FOLDER, TRAIN_UPLOAD_FOLDER
from src.utils.cursor_pagination import normalize_limit
from src.utils.data_transform import convert_firestore_doc
from src.utils.id_generator import (
    generate_audio_upload_id,
    generate_rvc_model_id,
    generate_train_job_id,
    generate_upload_session_id,
)
from src.utils.slugify import slugify
from src.utils.storage_helpers import (
    generate_signed_download_url,
    generate_signed_upload_url,
)

logger = logging.getLogger(__name__)

VALID_AUDIO_CONTENT_PREFIXES = ("audio/",)
VALID_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma"}
_PRIVATE_DROP_KEYS = ("storage_folder", "model_path", "index_path")


class InvalidTrainRequestError(Exception):
    pass


class TrainJobNotFoundError(Exception):
    pass


def _safe_filename(name: str) -> str:
    stem = Path(name or "audio.wav").stem
    ext = Path(name or "audio.wav").suffix.lower() or ".wav"
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("._-") or "audio"
    return "%s%s" % (stem[:80], ext)


def _assert_audio_file(name: str, content_type: str) -> None:
    ext = Path(name).suffix.lower()
    if ext not in VALID_AUDIO_EXTS:
        raise InvalidTrainRequestError(
            "audio file extension must be one of %s" % sorted(VALID_AUDIO_EXTS)
        )
    if content_type and not content_type.startswith(VALID_AUDIO_CONTENT_PREFIXES):
        guessed, _ = mimetypes.guess_type(name)
        if not guessed or not guessed.startswith("audio/"):
            raise InvalidTrainRequestError("contentType must be an audio/* type")


def _server_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _normalize_pretrained_path(path_value: str) -> str:
    if not path_value:
        return ""

    root = _server_root().resolve()
    assets_root = (root / "assets").resolve()
    candidate = Path(path_value)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved.relative_to(assets_root)
    except ValueError as exc:
        raise InvalidTrainRequestError(
            "pretrainedG/pretrainedD must point to a file under rvc_my_server/assets"
        ) from exc
    if not resolved.is_file():
        raise InvalidTrainRequestError("pretrained file does not exist: %s" % path_value)
    return str(resolved.relative_to(root)).replace("\\", "/")


def _public_job_view(doc: dict) -> dict:
    return convert_firestore_doc(doc, drop_keys=("audio_object_paths",))


def _private_model_view(doc: dict, include_signed_urls: bool = True) -> dict:
    view = convert_firestore_doc(doc, drop_keys=_PRIVATE_DROP_KEYS)
    if include_signed_urls:
        view["modelUrl"] = generate_signed_download_url(doc["model_path"])
        view["indexUrl"] = generate_signed_download_url(doc["index_path"])
        view["signedUrlExpiresIn"] = settings.SIGNED_DOWNLOAD_URL_EXPIRES_SECONDS
    return view


def create_training_upload_urls(
    body: CreateTrainUploadUrlsRequest,
    user_id: str,
) -> dict:
    upload_session_id = generate_upload_session_id()
    files = []

    for idx, item in enumerate(body.files):
        _assert_audio_file(item.file_name, item.content_type)
        audio_upload_id = generate_audio_upload_id()
        safe_name = _safe_filename(item.file_name)
        object_path = (
            f"{TRAIN_UPLOAD_FOLDER}/{user_id}/"
            f"{audio_upload_id}_{idx + 1:03d}_{safe_name}"
        )
        upload_url = generate_signed_upload_url(object_path, item.content_type)
        upload_doc = prepare_audio_upload_data(
            audio_upload_id=audio_upload_id,
            user_id=user_id,
            upload_session_id=upload_session_id,
            file_name=item.file_name,
            object_path=object_path,
            content_type=item.content_type,
        )
        add_audio_upload_to_firestore(upload_doc)
        files.append(
            {
                "audioUploadId": audio_upload_id,
                "fileName": item.file_name,
                "objectPath": object_path,
                "uploadUrl": upload_url,
                "method": "PUT",
                "headers": {"Content-Type": item.content_type},
                "expiresIn": settings.SIGNED_UPLOAD_URL_EXPIRES_SECONDS,
            }
        )

    return {"uploadSessionId": upload_session_id, "files": files}


def _validate_audio_object_paths(user_id: str, paths: list[str]) -> None:
    if len(set(paths)) != len(paths):
        raise InvalidTrainRequestError("audioObjectPaths must not contain duplicates")
    prefix = f"{TRAIN_UPLOAD_FOLDER}/{user_id}/"
    for path in paths:
        if not path.startswith(prefix):
            raise InvalidTrainRequestError(
                "audioObjectPaths must be created by this user via signed upload URLs"
            )
        ext = Path(path).suffix.lower()
        if ext not in VALID_AUDIO_EXTS:
            raise InvalidTrainRequestError("unsupported audio object extension: %s" % path)
    bucket = get_bucket()
    missing = [path for path in paths if not bucket.blob(path).exists()]
    if missing:
        raise InvalidTrainRequestError(
            "uploaded audio objects not found in Storage: %s" % missing
        )


def _resolve_audio_upload_ids(user_id: str, audio_upload_ids: list[str]) -> list[str]:
    if len(set(audio_upload_ids)) != len(audio_upload_ids):
        raise InvalidTrainRequestError("audioUploadIds must not contain duplicates")

    bucket = get_bucket()
    object_paths = []
    missing = []
    invalid = []

    for audio_upload_id in audio_upload_ids:
        doc = get_audio_upload_by_id(audio_upload_id)
        if not doc or doc.get("user_id") != user_id:
            invalid.append(audio_upload_id)
            continue

        object_path = doc.get("object_path", "")
        if not object_path or not bucket.blob(object_path).exists():
            missing.append(audio_upload_id)
            update_audio_upload_in_firestore(audio_upload_id, {"status": "missing"})
            continue

        update_audio_upload_in_firestore(audio_upload_id, {"status": "uploaded"})
        object_paths.append(object_path)

    if invalid:
        raise InvalidTrainRequestError(
            "audioUploadIds not found or not owned by current user: %s" % invalid
        )
    if missing:
        raise InvalidTrainRequestError(
            "audioUploadIds do not have uploaded Storage objects yet: %s" % missing
        )
    return object_paths


def _validate_user_upload_paths(user_id: str, paths: list[str]) -> None:
    if len(set(paths)) != len(paths):
        raise InvalidTrainRequestError("objectPaths must not contain duplicates")
    prefix = f"{TRAIN_UPLOAD_FOLDER}/{user_id}/"
    invalid = [path for path in paths if not path.startswith(prefix)]
    if invalid:
        raise InvalidTrainRequestError(
            "all objectPaths must belong to the current user under %s" % prefix
        )


def create_train_job(body: CreateTrainJobRequest, user_id: str) -> dict:
    title = body.title.strip()
    if not title:
        raise InvalidTrainRequestError("title is required")

    audio_object_paths = []
    if body.audio_upload_ids:
        audio_object_paths.extend(_resolve_audio_upload_ids(user_id, body.audio_upload_ids))
    if body.audio_object_paths:
        _validate_audio_object_paths(user_id, body.audio_object_paths)
        audio_object_paths.extend(body.audio_object_paths)
    if not audio_object_paths:
        raise InvalidTrainRequestError("audioUploadIds or audioObjectPaths is required")

    pretrained_g = _normalize_pretrained_path(body.pretrained_g.strip())
    pretrained_d = _normalize_pretrained_path(body.pretrained_d.strip())

    train_job_id = generate_train_job_id()
    params = {
        "sampleRate": body.sample_rate,
        "version": body.version,
        "ifF0": body.if_f0,
        "f0Method": body.f0_method,
        "totalEpochs": body.total_epochs,
        "saveEveryEpoch": body.save_every_epoch,
        "batchSize": body.batch_size,
        "numProcesses": body.num_processes,
        "gpuDevicesTrain": body.gpu_devices_train,
        "gpusForRmvpe": body.gpus_for_rmvpe,
        "speakerId": body.speaker_id,
        "saveOnlyLatest": body.save_only_latest,
        "cacheDatasetInGpu": body.cache_dataset_in_gpu,
        "saveWeightsEveryEpoch": body.save_weights_every_epoch,
        "pretrainedG": pretrained_g,
        "pretrainedD": pretrained_d,
        "preprocessPer": body.preprocess_per,
        "disablePreprocessParallel": body.disable_preprocess_parallel,
        "extractInfo": body.extract_info,
        "indexKmeansThreshold": body.index_kmeans_threshold,
        "indexKmeansCenters": body.index_kmeans_centers,
        "indexBatchSize": body.index_batch_size,
        "indexNprobe": body.index_nprobe,
        "audioUploadIds": body.audio_upload_ids or [],
    }
    doc = prepare_train_job_data(
        train_job_id=train_job_id,
        user_id=user_id,
        title=title,
        description=body.description,
        audio_object_paths=audio_object_paths,
        params=params,
    )
    add_train_job_to_firestore(doc)

    from src.tasks.train_tasks import train_rvc_model_task

    train_rvc_model_task.delay(train_job_id)
    return _public_job_view(doc)


def get_train_job_detail(train_job_id: str, user_id: str) -> dict:
    doc = get_train_job_by_id(train_job_id)
    if not doc or doc.get("user_id") != user_id:
        raise TrainJobNotFoundError("Training job not found")
    return _public_job_view(doc)


def list_train_jobs(user_id: str, limit: Optional[int], start_after: Optional[str]) -> dict:
    n = normalize_limit(limit)
    items, has_next = list_user_train_jobs_paginated(user_id, n, start_after)
    views = [_public_job_view(d) for d in items]
    next_cursor = items[-1].get("train_job_id") if has_next and items else None
    return {
        "paginatedItems": views,
        "pagination": {
            "limit": n,
            "hasNext": has_next,
            "nextCursor": next_cursor,
            "currentCount": len(views),
        },
    }


def list_uploaded_training_audios(user_id: str) -> dict:
    prefix = f"{TRAIN_UPLOAD_FOLDER}/{user_id}/"
    bucket = get_bucket()
    items = []
    known_paths = set()

    for doc in list_audio_uploads_by_user(user_id):
        object_path = doc.get("object_path", "")
        known_paths.add(object_path)
        blob = bucket.blob(object_path)
        exists = bool(object_path and blob.exists())
        if exists:
            blob.reload()
            status = "uploaded"
            update_audio_upload_in_firestore(doc["audio_upload_id"], {"status": status})
        else:
            blob = None
            status = "pending"

        items.append(
            {
                "audioUploadId": doc["audio_upload_id"],
                "uploadSessionId": doc.get("upload_session_id", ""),
                "fileName": doc.get("file_name") or Path(object_path).name,
                "objectPath": object_path,
                "contentType": (blob.content_type if blob else doc.get("content_type")) or "",
                "status": status,
                "sizeBytes": (blob.size if blob else 0) or 0,
                "createdAt": doc.get("created_at", ""),
                "updatedAt": (blob.updated.isoformat() if blob and blob.updated else doc.get("updated_at", "")),
                "audioUrl": generate_signed_download_url(object_path) if exists else "",
                "signedUrlExpiresIn": (
                    settings.SIGNED_DOWNLOAD_URL_EXPIRES_SECONDS if exists else 0
                ),
            }
        )

    legacy_blobs = [
        blob
        for blob in bucket.list_blobs(prefix=prefix)
        if Path(blob.name).suffix.lower() in VALID_AUDIO_EXTS and blob.name not in known_paths
    ]
    legacy_blobs.sort(key=lambda b: b.updated or b.time_created, reverse=True)
    for blob in legacy_blobs:
        items.append(
            {
                "audioUploadId": "",
                "uploadSessionId": "",
                "fileName": Path(blob.name).name,
                "objectPath": blob.name,
                "contentType": blob.content_type or "",
                "status": "uploaded",
                "sizeBytes": blob.size or 0,
                "createdAt": blob.time_created.isoformat() if blob.time_created else "",
                "updatedAt": blob.updated.isoformat() if blob.updated else "",
                "audioUrl": generate_signed_download_url(blob.name),
                "signedUrlExpiresIn": settings.SIGNED_DOWNLOAD_URL_EXPIRES_SECONDS,
            }
        )

    return {
        "items": items,
        "currentCount": len(items),
    }


def delete_uploaded_training_audios(
    user_id: str,
    object_paths: Optional[list[str]] = None,
    audio_upload_ids: Optional[list[str]] = None,
) -> dict:
    object_paths = object_paths or []
    audio_upload_ids = audio_upload_ids or []
    if not object_paths and not audio_upload_ids:
        raise InvalidTrainRequestError("audioUploadIds or objectPaths is required")

    resolved_paths = []
    invalid_ids = []
    for audio_upload_id in audio_upload_ids:
        doc = get_audio_upload_by_id(audio_upload_id)
        if not doc or doc.get("user_id") != user_id:
            invalid_ids.append(audio_upload_id)
            continue
        if doc.get("object_path"):
            resolved_paths.append(doc["object_path"])
    if invalid_ids:
        raise InvalidTrainRequestError(
            "audioUploadIds not found or not owned by current user: %s" % invalid_ids
        )

    all_paths = resolved_paths + object_paths
    _validate_user_upload_paths(user_id, all_paths)
    bucket = get_bucket()
    deleted = []
    not_found = []
    failed = []

    for object_path in all_paths:
        blob = bucket.blob(object_path)
        try:
            if not blob.exists():
                not_found.append(object_path)
                continue
            blob.delete()
            deleted.append(object_path)
        except Exception as exc:
            logger.warning("Failed to delete upload blob %s", object_path, exc_info=True)
            failed.append({"objectPath": object_path, "error": str(exc)})

    deleted_ids = []
    for audio_upload_id in audio_upload_ids:
        if delete_audio_upload_from_firestore(audio_upload_id):
            deleted_ids.append(audio_upload_id)

    return {
        "deletedCount": len(deleted),
        "deletedAudioUploadIds": deleted_ids,
        "deletedObjectPaths": deleted,
        "notFoundObjectPaths": not_found,
        "failedItems": failed,
    }


def delete_all_uploaded_training_audios(user_id: str) -> dict:
    prefix = f"{TRAIN_UPLOAD_FOLDER}/{user_id}/"
    bucket = get_bucket()
    blobs = list(bucket.list_blobs(prefix=prefix))
    deleted = []
    failed = []

    for blob in blobs:
        try:
            blob.delete()
            deleted.append(blob.name)
        except Exception as exc:
            logger.warning("Failed to delete upload blob %s", blob.name, exc_info=True)
            failed.append({"objectPath": blob.name, "error": str(exc)})

    deleted_docs = delete_audio_uploads_by_user(user_id)

    return {
        "deletedCount": len(deleted),
        "deletedAudioUploadIds": [
            doc.get("audio_upload_id", "") for doc in deleted_docs if doc.get("audio_upload_id")
        ],
        "deletedObjectPaths": deleted,
        "failedItems": failed,
    }


def get_private_rvc_model_detail(rvc_model_id: str, user_id: str) -> dict:
    doc = get_user_rvc_model_by_id(user_id, rvc_model_id)
    if not doc:
        raise TrainJobNotFoundError("Private RVC model not found")
    return _private_model_view(doc)


def list_private_rvc_models(
    user_id: str,
    limit: Optional[int],
    start_after: Optional[str],
) -> dict:
    n = normalize_limit(limit)
    items, has_next = list_user_rvc_models_paginated(user_id, n, start_after)
    views = [_private_model_view(d, include_signed_urls=False) for d in items]
    next_cursor = items[-1].get("rvc_model_id") if has_next and items else None
    return {
        "paginatedItems": views,
        "pagination": {
            "limit": n,
            "hasNext": has_next,
            "nextCursor": next_cursor,
            "currentCount": len(views),
        },
    }


def _job_root(train_job_id: str) -> Path:
    root = Path(settings.TRAIN_CACHE_DIR)
    if not root.is_absolute():
        root = Path(__file__).resolve().parent.parent.parent / root
    return (root / train_job_id).resolve()


def _download_training_inputs(job_doc: dict, job_root: Path) -> Path:
    input_dir = job_root / "inputs"
    if input_dir.exists():
        shutil.rmtree(input_dir)
    input_dir.mkdir(parents=True, exist_ok=True)

    bucket = get_bucket()
    for idx, object_path in enumerate(job_doc["audio_object_paths"]):
        ext = Path(object_path).suffix.lower() or ".wav"
        local_path = input_dir / ("input_%03d%s" % (idx + 1, ext))
        bucket.blob(object_path).download_to_filename(str(local_path))
    return input_dir


def _upload_private_artifact(local_path: Path, object_path: str, content_type: str) -> None:
    bucket = get_bucket()
    blob = bucket.blob(object_path)
    blob.upload_from_filename(str(local_path), content_type=content_type)


def execute_train_job(train_job_id: str) -> None:
    # Lazy import — only the worker container needs the heavy ML stack
    # (numpy, sklearn, torch via run_rvc_training_pipeline → infer_engine).
    # api-light imports execute_train_job only via from-import statements at
    # module load is fine because this function body is never called there.
    from src.services.rvc_train_pipeline import (
        RvcTrainingParams,
        run_rvc_training_pipeline,
    )

    job_doc = get_train_job_by_id(train_job_id)
    if not job_doc:
        raise TrainJobNotFoundError("Training job not found")
    if job_doc.get("status") not in {"queued", "failed"}:
        logger.info("Skip train job %s with status %s", train_job_id, job_doc.get("status"))
        return

    user_id = job_doc["user_id"]
    rvc_model_id = generate_rvc_model_id()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    publish_train_progress(
        train_job_id,
        "running",
        "download_inputs",
        5,
        "Downloading training audio from Storage",
        extra_updates={"started_at": started_at},
    )

    def progress(stage: str, value: int, message: str) -> None:
        publish_train_progress(train_job_id, "running", stage, value, message)

    try:
        job_root = _job_root(train_job_id)
        job_root.mkdir(parents=True, exist_ok=True)
        input_dir = _download_training_inputs(job_doc, job_root)
        params_doc = job_doc.get("params") or {}
        exp_name = "%s_%s" % (rvc_model_id, slugify(job_doc["title"])[:40])
        pipeline_params = RvcTrainingParams(
            experiment_name=exp_name,
            input_dir=input_dir,
            sample_rate=params_doc.get("sampleRate", "40k"),
            version=params_doc.get("version", "v2"),
            if_f0=bool(params_doc.get("ifF0", True)),
            speaker_id=int(params_doc.get("speakerId", 0)),
            num_processes=int(params_doc.get("numProcesses", 4)),
            f0_method=params_doc.get("f0Method", "rmvpe"),
            gpus_for_rmvpe=params_doc.get("gpusForRmvpe", "0"),
            gpu_devices_train=params_doc.get("gpuDevicesTrain", "0"),
            save_every_epoch=int(params_doc.get("saveEveryEpoch", 5)),
            total_epochs=int(params_doc.get("totalEpochs", 50)),
            batch_size=int(params_doc.get("batchSize", 4)),
            save_only_latest=bool(params_doc.get("saveOnlyLatest", True)),
            cache_dataset_in_gpu=bool(params_doc.get("cacheDatasetInGpu", False)),
            save_weights_every_epoch=bool(
                params_doc.get("saveWeightsEveryEpoch", False)
            ),
            pretrained_g=params_doc.get("pretrainedG", ""),
            pretrained_d=params_doc.get("pretrainedD", ""),
            preprocess_per=float(params_doc.get("preprocessPer", 3.7)),
            disable_preprocess_parallel=bool(
                params_doc.get("disablePreprocessParallel", False)
            ),
            extract_info=params_doc.get("extractInfo", "Extracted model."),
            index_kmeans_threshold=int(
                params_doc.get("indexKmeansThreshold", 200000)
            ),
            index_kmeans_centers=int(params_doc.get("indexKmeansCenters", 10000)),
            index_batch_size=int(params_doc.get("indexBatchSize", 8192)),
            index_nprobe=int(params_doc.get("indexNprobe", 1)),
        )

        model_local, index_local = run_rvc_training_pipeline(
            pipeline_params,
            output_model_name=rvc_model_id,
            progress=progress,
        )

        folder = f"{rvc_model_id}_{slugify(job_doc['title'])}"
        storage_prefix = f"{PRIVATE_RVC_MODEL_FOLDER}/{user_id}/{folder}"
        model_path = f"{storage_prefix}/model.pth"
        index_path = f"{storage_prefix}/model.index"

        progress("upload_artifacts", 97, "Uploading private model artifacts")
        _upload_private_artifact(model_local, model_path, "application/octet-stream")
        _upload_private_artifact(index_local, index_path, "application/octet-stream")

        model_doc = prepare_user_rvc_model_data(
            rvc_model_id=rvc_model_id,
            user_id=user_id,
            title=job_doc["title"],
            description=job_doc.get("description", ""),
            model_path=model_path,
            index_path=index_path,
            storage_folder=folder,
            train_job_id=train_job_id,
            params=params_doc,
        )
        add_user_rvc_model_to_firestore(model_doc)

        completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        publish_train_progress(
            train_job_id,
            "succeeded",
            "completed",
            100,
            "Training completed",
            rvc_model_id=rvc_model_id,
            extra_updates={"completed_at": completed_at},
        )
    except Exception as exc:
        logger.exception("Training job %s failed", train_job_id)
        completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        publish_train_progress(
            train_job_id,
            "failed",
            "failed",
            100,
            "Training failed",
            error=str(exc),
            extra_updates={"completed_at": completed_at},
        )
        raise
