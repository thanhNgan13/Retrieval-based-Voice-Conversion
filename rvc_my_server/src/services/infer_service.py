import logging
import time
import uuid as uuid_lib
from pathlib import Path
from typing import Tuple

import soundfile as sf
from fastapi import UploadFile

from src.config.firebase import get_bucket
from src.models.rvc_model_model import get_rvc_model_by_id
from src.services import infer_engine
from src.utils.storage_helpers import firebase_download_url

logger = logging.getLogger(__name__)

VALID_F0_METHODS = {"pm", "harvest", "crepe", "rmvpe"}


class ModelNotFoundError(Exception):
    pass


class InvalidInferRequestError(Exception):
    pass


class InferRuntimeError(Exception):
    pass


def _ensure_model_cached(rvc_model_id: str, model_doc: dict) -> Tuple[str, str]:
    """Download .pth and .index from Storage if not already in local cache.
    Returns (pth_filename_in_weight_root, index_local_absolute_path).
    """
    cache_paths = infer_engine.get_cache_paths()
    weights_dir = cache_paths["weights"]
    indices_dir = cache_paths["indices"]

    pth_filename = f"{rvc_model_id}.pth"
    index_filename = f"{rvc_model_id}.index"
    pth_local = weights_dir / pth_filename
    index_local = indices_dir / index_filename

    bucket = get_bucket()

    if not pth_local.is_file():
        model_path = model_doc.get("model_path")
        if not model_path:
            raise InferRuntimeError("RVC model record is missing 'model_path'")
        logger.info("Downloading %s → %s", model_path, pth_local)
        bucket.blob(model_path).download_to_filename(str(pth_local))

    if not index_local.is_file():
        index_path = model_doc.get("index_path")
        if not index_path:
            raise InferRuntimeError("RVC model record is missing 'index_path'")
        logger.info("Downloading %s → %s", index_path, index_local)
        bucket.blob(index_path).download_to_filename(str(index_local))

    return pth_filename, str(index_local)


def _save_upload_audio(audio_file: UploadFile, conversion_id: str) -> Path:
    cache_paths = infer_engine.get_cache_paths()
    inputs_dir = cache_paths["inputs"]
    ext = Path(audio_file.filename or "input.wav").suffix.lower() or ".wav"
    local_path = inputs_dir / f"{conversion_id}{ext}"

    audio_file.file.seek(0)
    with open(local_path, "wb") as f:
        while True:
            chunk = audio_file.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return local_path


def _upload_output_to_storage(local_path: Path, user_id: str, conversion_id: str) -> str:
    object_path = f"infer_outputs/{user_id}/{conversion_id}.wav"
    bucket = get_bucket()
    blob = bucket.blob(object_path)
    token = str(uuid_lib.uuid4())
    blob.metadata = {"firebaseStorageDownloadTokens": token}
    blob.upload_from_filename(str(local_path), content_type="audio/wav")
    return firebase_download_url(bucket.name, object_path, token)


def convert_voice(
    audio_file: UploadFile,
    rvc_model_id: str,
    speaker_id: int,
    f0_up_key: int,
    f0_method: str,
    index_rate: float,
    filter_radius: int,
    resample_sr: int,
    rms_mix_rate: float,
    protect: float,
    user_id: str,
) -> dict:
    if f0_method not in VALID_F0_METHODS:
        raise InvalidInferRequestError(
            f"f0Method must be one of {sorted(VALID_F0_METHODS)}"
        )
    if not audio_file or not audio_file.filename:
        raise InvalidInferRequestError("audio file is required")

    logger.info("[infer] looking up model %s in Firestore", rvc_model_id)
    model_doc = get_rvc_model_by_id(rvc_model_id)
    if not model_doc:
        raise ModelNotFoundError(f"RVC model '{rvc_model_id}' not found")

    conversion_id = f"conv_{int(time.time() * 1000)}_{uuid_lib.uuid4()}"
    logger.info("[infer] %s — saving uploaded audio to local cache", conversion_id)
    input_local = _save_upload_audio(audio_file, conversion_id)

    try:
        with infer_engine.engine_lock():
            logger.info("[infer] %s — acquiring engine (lazy init on first call)", conversion_id)
            vc, _config = infer_engine.get_engine()

            logger.info("[infer] %s — ensuring model .pth + .index cached locally", conversion_id)
            pth_filename, index_local_path = _ensure_model_cached(rvc_model_id, model_doc)

            # Only reload net_g when the requested model differs from the currently-loaded one.
            if infer_engine.get_current_model_id() != rvc_model_id:
                logger.info(
                    "[infer] %s — loading model into VC (vc.get_vc); this also loads Hubert on first call",
                    conversion_id,
                )
                t_load = time.time()
                vc.get_vc(pth_filename)
                infer_engine.set_current_model_id(rvc_model_id)
                logger.info(
                    "[infer] %s — model loaded in %.1fs", conversion_id, time.time() - t_load
                )
            else:
                logger.info(
                    "[infer] %s — model %s already loaded in engine, skipping reload",
                    conversion_id, rvc_model_id,
                )

            logger.info(
                "[infer] %s — running vc_single (f0=%s, key=%d, index_rate=%.2f) ...",
                conversion_id, f0_method, f0_up_key, index_rate,
            )
            t_start = time.time()
            info_text, audio_out = vc.vc_single(
                speaker_id,
                str(input_local),
                f0_up_key,
                None,  # f0_file — not exposed in API for now
                f0_method,
                index_local_path,
                "",  # file_index2 — unused (we always pass the explicit index path)
                index_rate,
                filter_radius,
                resample_sr,
                rms_mix_rate,
                protect,
            )
            elapsed_ms = int((time.time() - t_start) * 1000)
            logger.info(
                "[infer] %s — vc_single done in %d ms", conversion_id, elapsed_ms,
            )

            if audio_out is None:
                raise InferRuntimeError(info_text or "Inference failed")

            tgt_sr, audio_samples = audio_out

        cache_paths = infer_engine.get_cache_paths()
        output_local = cache_paths["outputs"] / f"{conversion_id}.wav"
        logger.info("[infer] %s — writing output WAV to %s", conversion_id, output_local)
        sf.write(str(output_local), audio_samples, tgt_sr)

        logger.info("[infer] %s — uploading output to storage", conversion_id)
        output_url = _upload_output_to_storage(output_local, user_id, conversion_id)
        logger.info("[infer] %s — done, returning outputUrl", conversion_id)

        return {
            "conversionId": conversion_id,
            "outputUrl": output_url,
            "outputSampleRate": tgt_sr,
            "durationMs": elapsed_ms,
            "info": info_text,
            "rvcModelId": rvc_model_id,
            "modelTitle": model_doc.get("title", ""),
            "params": {
                "speakerId": speaker_id,
                "f0UpKey": f0_up_key,
                "f0Method": f0_method,
                "indexRate": index_rate,
                "filterRadius": filter_radius,
                "resampleSr": resample_sr,
                "rmsMixRate": rms_mix_rate,
                "protect": protect,
            },
        }
    finally:
        try:
            input_local.unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to delete input cache %s", input_local, exc_info=True)
