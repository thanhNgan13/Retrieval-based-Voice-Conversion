import logging
import os
import shutil
import time
import uuid as uuid_lib
from pathlib import Path

import soundfile as sf

from src.config.firebase import get_bucket
from src.models.song_infer_job_model import get_song_infer_job_by_id
from src.models.user_rvc_model_model import (
    get_accessible_rvc_model_by_id,
    get_user_rvc_model_by_id,
)
from src.services import infer_engine
from src.services.infer_service import _build_model_cache_key, _ensure_model_cached
from src.services.mixing_service import (
    OUTPUT_CONTENT_TYPES,
    _add_audio_effects,
    _combine_audio,
)
from src.services.separation_service import (
    _assert_mdx_models_available,
    _onnx_providers,
    _run_mdx_standalone,
)
from src.services.list_cover_service import save_completed_cover
from src.services.song_infer_errors import SongInferJobNotFoundError, SongInferRuntimeError
from src.services.song_infer_progress import publish_song_infer_progress
from src.utils.constant import SONG_INFER_OUTPUT_FOLDER
from src.utils.storage_helpers import firebase_download_url

logger = logging.getLogger(__name__)


def _job_root(song_infer_job_id: str) -> Path:
    cache_paths = infer_engine.get_cache_paths()
    return (cache_paths["inputs"] / "song_infer_jobs" / song_infer_job_id).resolve()


def _download_input(job_doc: dict, job_root: Path) -> Path:
    input_dir = job_root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(job_doc["input_object_path"]).suffix.lower() or ".wav"
    local_path = input_dir / ("source_song%s" % ext)
    get_bucket().blob(job_doc["input_object_path"]).download_to_filename(str(local_path))
    return local_path


def _upload_job_output(
    local_path: Path,
    user_id: str,
    song_infer_job_id: str,
    key: str,
    content_type: str,
) -> dict:
    object_path = (
        f"{SONG_INFER_OUTPUT_FOLDER}/{user_id}/{song_infer_job_id}/"
        f"{key}{local_path.suffix.lower() or '.wav'}"
    )
    bucket = get_bucket()
    blob = bucket.blob(object_path)
    token = str(uuid_lib.uuid4())
    blob.metadata = {"firebaseStorageDownloadTokens": token}
    blob.upload_from_filename(str(local_path), content_type=content_type)
    return {
        "url": firebase_download_url(bucket.name, object_path, token),
        "objectPath": object_path,
        "fileName": local_path.name,
        "sizeBytes": local_path.stat().st_size,
    }


def _run_separation_stage(
    song_infer_job_id: str,
    input_local: Path,
    output_dir: Path,
    denoise: bool,
) -> dict[str, Path]:
    model_paths = _assert_mdx_models_available()
    providers = _onnx_providers()
    output_dir.mkdir(parents=True, exist_ok=True)

    publish_song_infer_progress(
        song_infer_job_id,
        "running",
        "separation_vocal_instrumental",
        12,
        "Separating vocal and instrumental with MDX-Net",
    )
    with infer_engine.engine_lock():
        vocals_path, instrumental_path = _run_mdx_standalone(
            output_dir=str(output_dir),
            model_path=model_paths["vocal"],
            filename=str(input_local),
            providers=providers,
            denoise=denoise,
        )

        publish_song_infer_progress(
            song_infer_job_id,
            "running",
            "separation_backup_main",
            24,
            "Separating backup vocals and main vocals",
        )
        backup_vocals_path, main_vocals_path = _run_mdx_standalone(
            output_dir=str(output_dir),
            model_path=model_paths["karaoke"],
            filename=vocals_path,
            providers=providers,
            suffix="Backup",
            invert_suffix="Main",
            denoise=denoise,
        )
        if vocals_path and os.path.exists(vocals_path):
            os.remove(vocals_path)

        publish_song_infer_progress(
            song_infer_job_id,
            "running",
            "separation_dereverb",
            34,
            "Dereverbing main vocals",
        )
        _, main_vocals_dereverb_path = _run_mdx_standalone(
            output_dir=str(output_dir),
            model_path=model_paths["dereverb"],
            filename=main_vocals_path,
            providers=providers,
            invert_suffix="DeReverb",
            exclude_main=True,
            denoise=denoise,
        )
        if main_vocals_path and os.path.exists(main_vocals_path):
            os.remove(main_vocals_path)

    return {
        "instrumental": Path(instrumental_path),
        "backupVocals": Path(backup_vocals_path),
        "mainVocalsDereverb": Path(main_vocals_dereverb_path),
    }


def _run_voice_conversion_stage(
    song_infer_job_id: str,
    job_doc: dict,
    input_local: Path,
    output_dir: Path,
) -> dict:
    params = job_doc["params"]["infer"]
    user_id = job_doc["user_id"]
    rvc_model_id = job_doc["rvc_model_id"]
    private_only = bool(params.get("privateOnly", False))

    if private_only:
        model_doc = get_user_rvc_model_by_id(user_id, rvc_model_id)
    else:
        model_doc = get_accessible_rvc_model_by_id(user_id, rvc_model_id)
    if not model_doc:
        raise SongInferRuntimeError("RVC model '%s' not found" % rvc_model_id)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_local = output_dir / "converted_main_vocal.wav"

    with infer_engine.engine_lock():
        publish_song_infer_progress(
            song_infer_job_id,
            "running",
            "infer_load_model",
            45,
            "Loading RVC model",
        )
        vc, _config = infer_engine.get_engine()
        model_cache_key = _build_model_cache_key(user_id, rvc_model_id, model_doc)
        pth_filename, index_local_path = _ensure_model_cached(model_cache_key, model_doc)

        if infer_engine.get_current_model_id() != model_cache_key:
            vc.get_vc(pth_filename)
            infer_engine.set_current_model_id(model_cache_key)

        publish_song_infer_progress(
            song_infer_job_id,
            "running",
            "infer_convert_voice",
            58,
            "Converting main vocals to target RVC voice",
        )
        t_start = time.time()
        info_text, audio_out = vc.vc_single(
            int(params["speakerId"]),
            str(input_local),
            int(params["f0UpKey"]),
            None,
            params["f0Method"],
            index_local_path,
            "",
            float(params["indexRate"]),
            int(params["filterRadius"]),
            int(params["resampleSr"]),
            float(params["rmsMixRate"]),
            float(params["protect"]),
        )
        elapsed_ms = int((time.time() - t_start) * 1000)

    if audio_out is None:
        raise SongInferRuntimeError(info_text or "RVC inference failed")

    tgt_sr, audio_samples = audio_out
    sf.write(str(output_local), audio_samples, tgt_sr)
    return {
        "localPath": output_local,
        "outputSampleRate": tgt_sr,
        "durationMs": elapsed_ms,
        "info": info_text,
        "modelTitle": model_doc.get("title", ""),
    }


def _run_mixing_stage(
    song_infer_job_id: str,
    job_doc: dict,
    converted_vocal_path: Path,
    backup_vocal_path: Path,
    instrumental_path: Path,
    output_dir: Path,
) -> dict:
    params = job_doc["params"]["mixing"]
    output_format = params["outputFormat"]
    output_dir.mkdir(parents=True, exist_ok=True)

    wet_vocal_local = output_dir / "ai_vocals_with_effects.wav"
    final_mix_local = output_dir / ("final_cover.%s" % output_format)

    publish_song_infer_progress(
        song_infer_job_id,
        "running",
        "mixing_effects",
        78,
        "Applying highpass, compressor and reverb to converted vocals",
    )
    _add_audio_effects(
        input_path=converted_vocal_path,
        output_path=wet_vocal_local,
        reverb_room_size=float(params["reverbRoomSize"]),
        reverb_wet=float(params["reverbWetLevel"]),
        reverb_dry=float(params["reverbDryLevel"]),
        reverb_damping=float(params["reverbDamping"]),
    )

    publish_song_infer_progress(
        song_infer_job_id,
        "running",
        "mixing_overlay",
        86,
        "Overlaying converted vocals, backup vocals and instrumental",
    )
    mixed_audio = _combine_audio(
        main_vocal_path=wet_vocal_local,
        backup_vocal_path=backup_vocal_path,
        instrumental_path=instrumental_path,
        output_path=final_mix_local,
        main_gain=float(params["mainGain"]),
        backup_gain=float(params["backupGain"]),
        inst_gain=float(params["instGain"]),
        output_format=output_format,
    )
    return {
        "wetVocalPath": wet_vocal_local,
        "finalMixPath": final_mix_local,
        "audioInfo": {
            "durationMs": len(mixed_audio),
            "frameRate": mixed_audio.frame_rate,
            "channels": mixed_audio.channels,
            "sampleWidth": mixed_audio.sample_width,
        },
    }


def execute_song_infer_job(song_infer_job_id: str) -> None:
    job_doc = get_song_infer_job_by_id(song_infer_job_id)
    if not job_doc:
        raise SongInferJobNotFoundError("Song inference job not found")
    if job_doc.get("status") not in {"queued", "failed"}:
        logger.info(
            "Skip song infer job %s with status %s",
            song_infer_job_id,
            job_doc.get("status"),
        )
        return

    user_id = job_doc["user_id"]
    params = job_doc.get("params") or {}
    separation_params = params.get("separation") or {}
    mixing_params = params.get("mixing") or {}
    output_format = mixing_params.get("outputFormat", "wav")
    job_root = _job_root(song_infer_job_id)
    outputs: dict = {}

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    publish_song_infer_progress(
        song_infer_job_id,
        "running",
        "download_input",
        5,
        "Downloading source song from Storage",
        extra_updates={"started_at": started_at},
    )

    try:
        if job_root.exists():
            shutil.rmtree(job_root)
        job_root.mkdir(parents=True, exist_ok=True)

        input_local = _download_input(job_doc, job_root)
        separated = _run_separation_stage(
            song_infer_job_id=song_infer_job_id,
            input_local=input_local,
            output_dir=job_root / "separation",
            denoise=bool(separation_params.get("denoise", True)),
        )

        publish_song_infer_progress(
            song_infer_job_id,
            "running",
            "upload_separation_outputs",
            40,
            "Uploading separated stems",
        )
        outputs["separation"] = {
            key: _upload_job_output(path, user_id, song_infer_job_id, key, "audio/wav")
            for key, path in separated.items()
        }
        publish_song_infer_progress(
            song_infer_job_id,
            "running",
            "separation_completed",
            42,
            "Audio separation completed",
            outputs=outputs,
        )

        conversion = _run_voice_conversion_stage(
            song_infer_job_id=song_infer_job_id,
            job_doc=job_doc,
            input_local=separated["mainVocalsDereverb"],
            output_dir=job_root / "infer",
        )
        converted_payload = _upload_job_output(
            conversion["localPath"],
            user_id,
            song_infer_job_id,
            "convertedMainVocals",
            "audio/wav",
        )
        converted_payload.update(
            {
                "outputSampleRate": conversion["outputSampleRate"],
                "durationMs": conversion["durationMs"],
                "info": conversion["info"],
                "modelTitle": conversion["modelTitle"],
            }
        )
        outputs["infer"] = {"convertedMainVocals": converted_payload}
        publish_song_infer_progress(
            song_infer_job_id,
            "running",
            "infer_completed",
            72,
            "Voice conversion completed",
            outputs=outputs,
        )

        mixing = _run_mixing_stage(
            song_infer_job_id=song_infer_job_id,
            job_doc=job_doc,
            converted_vocal_path=conversion["localPath"],
            backup_vocal_path=separated["backupVocals"],
            instrumental_path=separated["instrumental"],
            output_dir=job_root / "mixing",
        )

        publish_song_infer_progress(
            song_infer_job_id,
            "running",
            "upload_mixing_outputs",
            95,
            "Uploading final mix outputs",
            outputs=outputs,
        )
        outputs["mixing"] = {
            "aiVocalsWet": _upload_job_output(
                mixing["wetVocalPath"],
                user_id,
                song_infer_job_id,
                "aiVocalsWet",
                "audio/wav",
            ),
            "finalMix": _upload_job_output(
                mixing["finalMixPath"],
                user_id,
                song_infer_job_id,
                "finalMix",
                OUTPUT_CONTENT_TYPES.get(output_format, "application/octet-stream"),
            ),
            "audioInfo": mixing["audioInfo"],
        }

        completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        publish_song_infer_progress(
            song_infer_job_id,
            "running",
            "save_cover",
            98,
            "Saving completed cover metadata",
            outputs=outputs,
        )
        save_completed_cover(job_doc, outputs, completed_at)
        publish_song_infer_progress(
            song_infer_job_id,
            "succeeded",
            "completed",
            100,
            "Song inference pipeline completed",
            outputs=outputs,
            extra_updates={"completed_at": completed_at},
        )
    except Exception as exc:
        logger.exception("Song infer job %s failed", song_infer_job_id)
        completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        publish_song_infer_progress(
            song_infer_job_id,
            "failed",
            "failed",
            100,
            "Song inference pipeline failed",
            outputs=outputs,
            error=str(exc),
            extra_updates={"completed_at": completed_at},
        )
        raise
    finally:
        if not bool(separation_params.get("keepLocal", False)) and not bool(
            mixing_params.get("keepLocal", False)
        ):
            try:
                shutil.rmtree(job_root, ignore_errors=True)
            except Exception:
                logger.warning("Failed to delete song infer job cache %s", job_root, exc_info=True)
