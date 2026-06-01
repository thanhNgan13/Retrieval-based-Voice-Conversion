import logging
import re
import shutil
import time
import uuid as uuid_lib
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from src.config.firebase import get_bucket
from src.services import infer_engine
from src.utils.storage_helpers import firebase_download_url

logger = logging.getLogger(__name__)

VALID_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma"}
VALID_OUTPUT_FORMATS = {
    "wav": "audio/wav",
    "flac": "audio/flac",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
}
DEFAULT_UVR5_MODEL = "HP2_all_vocals"


class InvalidSeparationRequestError(Exception):
    pass


class SeparationRuntimeError(Exception):
    pass


def _safe_filename(name: str) -> str:
    stem = Path(name or "song.wav").stem
    ext = Path(name or "song.wav").suffix.lower() or ".wav"
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("._-") or "song"
    return "%s%s" % (stem[:80], ext)


def _assert_audio_file(audio_file: UploadFile) -> None:
    if not audio_file or not audio_file.filename:
        raise InvalidSeparationRequestError("audio file is required")
    ext = Path(audio_file.filename).suffix.lower()
    if ext not in VALID_AUDIO_EXTS:
        raise InvalidSeparationRequestError(
            "audio file extension must be one of %s" % sorted(VALID_AUDIO_EXTS)
        )


def _save_upload_audio(audio_file: UploadFile, input_dir: Path) -> Path:
    input_dir.mkdir(parents=True, exist_ok=True)
    local_path = input_dir / _safe_filename(audio_file.filename or "song.wav")

    audio_file.file.seek(0)
    with open(local_path, "wb") as f:
        while True:
            chunk = audio_file.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return local_path


def _uvr5_weight_root() -> Path:
    return infer_engine.get_assets_root() / "uvr5_weights"


def list_uvr5_models() -> dict:
    weight_root = _uvr5_weight_root()
    return {
        "defaultModel": DEFAULT_UVR5_MODEL,
        "models": sorted(path.stem for path in weight_root.glob("*.pth")),
        "weightRoot": str(weight_root),
    }


def _assert_uvr5_model_available(model_name: str) -> None:
    if not model_name or not re.match(r"^[A-Za-z0-9_.+-]+$", model_name):
        raise InvalidSeparationRequestError("modelName contains invalid characters")

    weight_root = _uvr5_weight_root()
    model_path = weight_root / ("%s.pth" % model_name)

    if not model_path.is_file():
        raise InvalidSeparationRequestError(
            "UVR5 model '%s' is not installed. Call admin /setup-uvr5-assets first."
            % model_name
        )


def _single_output_file(root: Path, label: str) -> Path:
    files = sorted(path for path in root.iterdir() if path.is_file())
    if not files:
        raise SeparationRuntimeError("UVR5 did not produce %s output" % label)
    if len(files) > 1:
        logger.warning("UVR5 produced multiple %s outputs, using %s", label, files[0])
    return files[0]


def _upload_output(local_path: Path, user_id: str, separation_id: str, stem: str) -> str:
    ext = local_path.suffix.lower().lstrip(".") or "wav"
    object_path = f"separation_outputs/{user_id}/{separation_id}/{stem}.{ext}"
    bucket = get_bucket()
    blob = bucket.blob(object_path)
    token = str(uuid_lib.uuid4())
    blob.metadata = {"firebaseStorageDownloadTokens": token}
    blob.upload_from_filename(
        str(local_path),
        content_type=VALID_OUTPUT_FORMATS.get(ext, "application/octet-stream"),
    )
    return firebase_download_url(bucket.name, object_path, token)


def separate_song(
    audio_file: UploadFile,
    user_id: str,
    model_name: str = DEFAULT_UVR5_MODEL,
    agg: int = 10,
    output_format: str = "wav",
    keep_local: bool = False,
) -> dict:
    _assert_audio_file(audio_file)

    output_format = output_format.lower().strip()
    if output_format not in VALID_OUTPUT_FORMATS:
        raise InvalidSeparationRequestError(
            "outputFormat must be one of %s" % sorted(VALID_OUTPUT_FORMATS)
        )
    if agg < 0 or agg > 20:
        raise InvalidSeparationRequestError("agg must be between 0 and 20")

    model_name = model_name.strip() or DEFAULT_UVR5_MODEL
    _assert_uvr5_model_available(model_name)

    separation_id = f"sep_{int(time.time() * 1000)}_{uuid_lib.uuid4()}"
    cache_paths = infer_engine.get_cache_paths()
    work_dir = cache_paths["inputs"] / "separation" / separation_id
    input_dir = work_dir / "input"
    vocal_dir = work_dir / "vocal"
    instrumental_dir = work_dir / "instrumental"
    local_input: Optional[Path] = None
    elapsed_ms = 0
    final_log = ""

    try:
        local_input = _save_upload_audio(audio_file, input_dir)
        vocal_dir.mkdir(parents=True, exist_ok=True)
        instrumental_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "[separation] %s — running UVR5 model=%s agg=%d format=%s",
            separation_id,
            model_name,
            agg,
            output_format,
        )
        t_start = time.time()
        with infer_engine.engine_lock():
            # Build Config before importing UVR5 modules; their module-level Config()
            # then reuses the same singleton with sanitized argv.
            infer_engine.get_config()
            from infer.modules.uvr5.modules import uvr

            for info in uvr(
                model_name,
                str(input_dir),
                str(vocal_dir),
                [],
                str(instrumental_dir),
                agg,
                output_format,
            ):
                final_log = info

        elapsed_ms = int((time.time() - t_start) * 1000)
        vocal_local = _single_output_file(vocal_dir, "vocal")
        instrumental_local = _single_output_file(instrumental_dir, "instrumental")

        logger.info("[separation] %s — uploading outputs to Storage", separation_id)
        vocal_url = _upload_output(vocal_local, user_id, separation_id, "vocal")
        instrumental_url = _upload_output(
            instrumental_local,
            user_id,
            separation_id,
            "instrumental",
        )

        return {
            "separationId": separation_id,
            "modelName": model_name,
            "agg": agg,
            "outputFormat": output_format,
            "durationMs": elapsed_ms,
            "inputFileName": audio_file.filename,
            "outputs": {
                "vocal": {
                    "url": vocal_url,
                    "fileName": vocal_local.name,
                    "sizeBytes": vocal_local.stat().st_size,
                },
                "instrumental": {
                    "url": instrumental_url,
                    "fileName": instrumental_local.name,
                    "sizeBytes": instrumental_local.stat().st_size,
                },
            },
            "info": final_log,
        }
    except InvalidSeparationRequestError:
        raise
    except Exception as exc:
        logger.exception("[separation] %s failed", separation_id)
        raise SeparationRuntimeError(str(exc)) from exc
    finally:
        if not keep_local:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                logger.warning("Failed to delete separation cache %s", work_dir, exc_info=True)
        elif local_input:
            logger.info("[separation] kept local workspace at %s", work_dir)
