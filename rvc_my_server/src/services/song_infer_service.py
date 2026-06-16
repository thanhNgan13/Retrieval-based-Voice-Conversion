import logging
import mimetypes
import re
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from src.config.firebase import get_bucket, get_db
from src.models.song_infer_job_model import (
    add_song_infer_job_to_firestore,
    get_song_infer_job_by_id,
    list_user_song_infer_jobs_paginated,
    prepare_song_infer_job_data,
)
from src.models.user_rvc_model_model import (
    get_accessible_rvc_model_by_id,
    get_user_rvc_model_by_id,
)
from src.services.song_infer_errors import (
    InvalidSongInferRequestError,
    SongInferJobNotFoundError,
)
from src.services.list_cover_service import list_covers
from src.utils.constant import SONG_INFER_INPUT_FOLDER
from src.utils.cursor_pagination import normalize_limit
from src.utils.data_transform import convert_firestore_doc
from src.utils.id_generator import generate_song_infer_job_id

logger = logging.getLogger(__name__)

VALID_AUDIO_CONTENT_PREFIXES = ("audio/",)
VALID_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma"}
VALID_F0_METHODS = {"pm", "harvest", "crepe", "rmvpe"}
VALID_OUTPUT_FORMATS = {"wav", "mp3"}


def _safe_filename(name: str) -> str:
    stem = Path(name or "song.wav").stem
    ext = Path(name or "song.wav").suffix.lower() or ".wav"
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("._-") or "song"
    return "%s%s" % (stem[:80], ext)


def _assert_audio_upload(song_file: UploadFile) -> None:
    if not song_file or not song_file.filename:
        raise InvalidSongInferRequestError("song file is required")
    ext = Path(song_file.filename).suffix.lower()
    if ext not in VALID_AUDIO_EXTS:
        raise InvalidSongInferRequestError(
            "song file extension must be one of %s" % sorted(VALID_AUDIO_EXTS)
        )
    content_type = song_file.content_type or ""
    if content_type and not content_type.startswith(VALID_AUDIO_CONTENT_PREFIXES):
        guessed, _ = mimetypes.guess_type(song_file.filename)
        if not guessed or not guessed.startswith("audio/"):
            raise InvalidSongInferRequestError("song contentType must be an audio/* type")


def _validate_unit_interval(value: float, name: str) -> None:
    if value < 0.0 or value > 1.0:
        raise InvalidSongInferRequestError("%s must be between 0.0 and 1.0" % name)


def _validate_params(params: dict) -> None:
    infer_params = params["infer"]
    mixing_params = params["mixing"]
    if infer_params["f0Method"] not in VALID_F0_METHODS:
        raise InvalidSongInferRequestError(
            "f0Method must be one of %s" % sorted(VALID_F0_METHODS)
        )
    output_format = mixing_params["outputFormat"].lower().strip()
    if output_format not in VALID_OUTPUT_FORMATS:
        raise InvalidSongInferRequestError(
            "outputFormat must be one of %s" % sorted(VALID_OUTPUT_FORMATS)
        )
    mixing_params["outputFormat"] = output_format
    for key in ("reverbRoomSize", "reverbWetLevel", "reverbDryLevel", "reverbDamping"):
        _validate_unit_interval(float(mixing_params[key]), key)


def _public_job_view(doc: dict) -> dict:
    return convert_firestore_doc(doc, drop_keys=("input_object_path",))


def _upload_input(song_file: UploadFile, user_id: str, song_infer_job_id: str) -> str:
    safe_name = _safe_filename(song_file.filename or "song.wav")
    object_path = f"{SONG_INFER_INPUT_FOLDER}/{user_id}/{song_infer_job_id}_{safe_name}"
    bucket = get_bucket()
    blob = bucket.blob(object_path)
    song_file.file.seek(0)
    blob.upload_from_file(
        song_file.file,
        content_type=song_file.content_type or mimetypes.guess_type(safe_name)[0] or "audio/wav",
    )
    return object_path


def create_song_infer_job(
    song_file: UploadFile,
    rvc_model_id: str,
    user_id: str,
    params: dict,
) -> dict:
    _assert_audio_upload(song_file)
    _validate_params(params)

    private_only = bool(params["infer"].get("privateOnly", False))
    if private_only:
        model_doc = get_user_rvc_model_by_id(user_id, rvc_model_id)
    else:
        model_doc = get_accessible_rvc_model_by_id(user_id, rvc_model_id)
    if not model_doc:
        raise InvalidSongInferRequestError("RVC model '%s' not found" % rvc_model_id)

    song_infer_job_id = generate_song_infer_job_id()
    input_object_path = _upload_input(song_file, user_id, song_infer_job_id)
    doc = prepare_song_infer_job_data(
        song_infer_job_id=song_infer_job_id,
        user_id=user_id,
        input_object_path=input_object_path,
        input_file_name=song_file.filename or "song.wav",
        rvc_model_id=rvc_model_id,
        params=params,
        song_info=None,
    )
    add_song_infer_job_to_firestore(doc)
    # Scheduler picks this up on its next tick (or immediately via Redis trigger).
    return _public_job_view(doc)


def get_song_infer_job_detail(song_infer_job_id: str, user_id: str) -> dict:
    doc = get_song_infer_job_by_id(song_infer_job_id)
    if not doc or doc.get("user_id") != user_id:
        raise SongInferJobNotFoundError("Song inference job not found")
    return _public_job_view(doc)


def list_song_infer_jobs(user_id: str, limit: Optional[int], start_after: Optional[str]) -> dict:
    n = normalize_limit(limit)
    items, has_next = list_user_song_infer_jobs_paginated(user_id, n, start_after)
    views = [_public_job_view(d) for d in items]
    next_cursor = items[-1].get("song_infer_job_id") if has_next and items else None
    return {
        "paginatedItems": views,
        "pagination": {
            "limit": n,
            "hasNext": has_next,
            "nextCursor": next_cursor,
            "currentCount": len(views),
        },
    }


def list_completed_covers(user_id: str, limit: Optional[int], start_after: Optional[str]) -> dict:
    return list_covers(user_id, limit, start_after)


# ---------------------------------------------------------------------------
# Helpers for song-ID-based infer
# ---------------------------------------------------------------------------

def _get_song_by_id(song_id: str) -> Optional[dict]:
    """Query Firestore collectionGroup('songs') to find a song by its id field."""
    db = get_db()
    snaps = (
        db.collection_group("songs")
        .where(filter=("id", "==", song_id))
        .limit(1)
        .get()
    )
    if not snaps:
        return None
    return snaps[0].to_dict()


def _build_params_from_schema(body) -> dict:
    """Convert CreateSongInferFromSongIdsRequest fields into the internal params dict."""
    return {
        "separation": {
            "denoise": body.separationDenoise,
            "keepLocal": body.separationKeepLocal,
            "pipeline": "MDX-Net 3-stage notebook pipeline",
            "sampleRate": 44100,
            "models": {
                "vocal": "UVR-MDX-NET-Voc_FT.onnx",
                "karaoke": "UVR_MDXNET_KARA_2.onnx",
                "dereverb": "Reverb_HQ_By_FoxJoy.onnx",
            },
        },
        "infer": {
            "privateOnly": body.privateOnly,
            "speakerId": body.speakerId,
            "f0UpKey": body.f0UpKey,
            "f0Method": body.f0Method,
            "indexRate": body.indexRate,
            "filterRadius": body.filterRadius,
            "resampleSr": body.resampleSr,
            "rmsMixRate": body.rmsMixRate,
            "protect": body.protect,
        },
        "mixing": {
            "keepLocal": body.mixingKeepLocal,
            "reverbRoomSize": body.reverbRoomSize,
            "reverbWetLevel": body.reverbWetLevel,
            "reverbDryLevel": body.reverbDryLevel,
            "reverbDamping": body.reverbDamping,
            "mainGain": body.mainGain,
            "backupGain": body.backupGain,
            "instGain": body.instGain,
            "outputFormat": body.outputFormat,
            "notebookBaseMainDb": -4,
            "notebookBaseBackupDb": -6,
            "notebookBaseInstrumentalDb": -7,
            "effects": {
                "highpassFilter": {"enabled": True},
                "compressor": {"ratio": 4, "thresholdDb": -15},
            },
        },
    }


def create_song_infer_job_from_song_id(body, user_id: str) -> dict:
    """Create one infer job from a Firestore song ID. Input audio is fetched from audioUrl."""
    _validate_params(_build_params_from_schema(body))

    rvc_model_id = body.rvcModelId
    private_only = body.privateOnly
    if private_only:
        model_doc = get_user_rvc_model_by_id(user_id, rvc_model_id)
    else:
        model_doc = get_accessible_rvc_model_by_id(user_id, rvc_model_id)
    if not model_doc:
        raise InvalidSongInferRequestError("RVC model '%s' not found" % rvc_model_id)

    song_doc = _get_song_by_id(body.songId)
    if not song_doc:
        raise InvalidSongInferRequestError("Song '%s' not found" % body.songId)

    audio_url = song_doc.get("audioUrl") or ""
    if not audio_url:
        raise InvalidSongInferRequestError("Song '%s' has no audioUrl" % body.songId)

    title = song_doc.get("title") or body.songId
    safe_title = re.sub(r"[^a-zA-Z0-9._-]+", "_", title).strip("._-") or "song"
    input_file_name = "%s.mp3" % safe_title[:80]

    song_infer_job_id = generate_song_infer_job_id()
    doc = prepare_song_infer_job_data(
        song_infer_job_id=song_infer_job_id,
        user_id=user_id,
        input_object_path="",
        input_file_name=input_file_name,
        rvc_model_id=rvc_model_id,
        params=_build_params_from_schema(body),
        input_url=audio_url,
        source_song_id=body.songId,
        song_info={
            "id": song_doc.get("id", ""),
            "title": song_doc.get("title", ""),
            "artists": song_doc.get("artists", []),
            "duration": song_doc.get("duration", ""),
            "coverImage": song_doc.get("coverImage", ""),
            "audioUrl": song_doc.get("audioUrl", ""),
            "playlistId": song_doc.get("playlistId", ""),
            "uploader": song_doc.get("uploader", ""),
        },
    )
    add_song_infer_job_to_firestore(doc)
    return _public_job_view(doc)
