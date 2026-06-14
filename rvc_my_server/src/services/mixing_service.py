import logging
import re
import shutil
import time
import uuid as uuid_lib
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from pedalboard import Compressor, HighpassFilter, Pedalboard, Reverb
from pedalboard.io import AudioFile
from pydub import AudioSegment

from src.config.firebase import get_bucket
from src.services import infer_engine
from src.utils.storage_helpers import firebase_download_url

logger = logging.getLogger(__name__)

VALID_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma"}
VALID_OUTPUT_FORMATS = {"wav", "mp3"}
OUTPUT_CONTENT_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
}


class InvalidMixingRequestError(Exception):
    pass


class MixingRuntimeError(Exception):
    pass


def _safe_filename(name: str, fallback: str) -> str:
    path = Path(name or fallback)
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", path.stem).strip("._-") or Path(fallback).stem
    ext = path.suffix.lower() or Path(fallback).suffix.lower() or ".wav"
    return "%s%s" % (stem[:80], ext)


def _assert_audio_file(audio_file: UploadFile, field_name: str) -> None:
    if not audio_file or not audio_file.filename:
        raise InvalidMixingRequestError("%s file is required" % field_name)
    ext = Path(audio_file.filename).suffix.lower()
    if ext not in VALID_AUDIO_EXTS:
        raise InvalidMixingRequestError(
            "%s extension must be one of %s" % (field_name, sorted(VALID_AUDIO_EXTS))
        )


def _assert_optional_audio_file(audio_file: Optional[UploadFile], field_name: str) -> None:
    if audio_file is None or not audio_file.filename:
        return
    _assert_audio_file(audio_file, field_name)


def _validate_unit_interval(value: float, name: str) -> None:
    if value < 0.0 or value > 1.0:
        raise InvalidMixingRequestError("%s must be between 0.0 and 1.0" % name)


def _save_upload_audio(audio_file: UploadFile, input_dir: Path, fallback: str) -> Path:
    input_dir.mkdir(parents=True, exist_ok=True)
    local_path = input_dir / _safe_filename(audio_file.filename or fallback, fallback)

    audio_file.file.seek(0)
    with open(local_path, "wb") as f:
        while True:
            chunk = audio_file.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return local_path


def _save_optional_upload_audio(
    audio_file: Optional[UploadFile],
    input_dir: Path,
    fallback: str,
) -> Optional[Path]:
    if audio_file is None or not audio_file.filename:
        return None
    return _save_upload_audio(audio_file, input_dir, fallback)


def _add_audio_effects(
    input_path: Path,
    output_path: Path,
    reverb_room_size: float = 0.15,
    reverb_wet: float = 0.2,
    reverb_dry: float = 0.8,
    reverb_damping: float = 0.7,
) -> Path:
    board = Pedalboard(
        [
            HighpassFilter(),
            Compressor(ratio=4, threshold_db=-15),
            Reverb(
                room_size=reverb_room_size,
                dry_level=reverb_dry,
                wet_level=reverb_wet,
                damping=reverb_damping,
            ),
        ]
    )

    with AudioFile(str(input_path)) as f:
        with AudioFile(str(output_path), "w", f.samplerate, f.num_channels) as o:
            while f.tell() < f.frames:
                chunk = f.read(int(f.samplerate))
                effected = board(chunk, f.samplerate, reset=False)
                o.write(effected)

    return output_path


def _combine_audio(
    main_vocal_path: Path,
    backup_vocal_path: Optional[Path],
    instrumental_path: Optional[Path],
    output_path: Path,
    main_gain: float = 0,
    backup_gain: float = 0,
    inst_gain: float = 0,
    output_format: str = "wav",
) -> AudioSegment:
    main_vocal_audio = AudioSegment.from_file(str(main_vocal_path)) - 4 + main_gain

    if backup_vocal_path and backup_vocal_path.exists():
        backup_vocal_audio = AudioSegment.from_file(str(backup_vocal_path)) - 6 + backup_gain
    else:
        backup_vocal_audio = AudioSegment.silent(duration=len(main_vocal_audio))

    if instrumental_path and instrumental_path.exists():
        instrumental_audio = AudioSegment.from_file(str(instrumental_path)) - 7 + inst_gain
    else:
        instrumental_audio = AudioSegment.silent(duration=len(main_vocal_audio))

    mixed_audio = main_vocal_audio.overlay(backup_vocal_audio).overlay(instrumental_audio)
    mixed_audio.export(str(output_path), format=output_format)
    return mixed_audio


def _upload_output(local_path: Path, user_id: str, mixing_id: str, key: str, output_format: str) -> str:
    object_path = f"mixing_outputs/{user_id}/{mixing_id}/{key}.{output_format}"
    bucket = get_bucket()
    blob = bucket.blob(object_path)
    token = str(uuid_lib.uuid4())
    blob.metadata = {"firebaseStorageDownloadTokens": token}
    blob.upload_from_filename(
        str(local_path),
        content_type=OUTPUT_CONTENT_TYPES.get(output_format, "application/octet-stream"),
    )
    return firebase_download_url(bucket.name, object_path, token)


def _output_payload(local_path: Path, url: str, output_format: str) -> dict:
    return {
        "url": url,
        "fileName": local_path.name,
        "format": output_format,
        "sizeBytes": local_path.stat().st_size,
    }


def mix_ai_cover(
    main_vocal_file: UploadFile,
    backup_vocal_file: Optional[UploadFile],
    instrumental_file: Optional[UploadFile],
    user_id: str,
    reverb_room_size: float = 0.15,
    reverb_wet: float = 0.2,
    reverb_dry: float = 0.8,
    reverb_damping: float = 0.7,
    main_gain: float = 0,
    backup_gain: float = 0,
    inst_gain: float = 0,
    output_format: str = "wav",
    keep_local: bool = False,
) -> dict:
    _assert_audio_file(main_vocal_file, "mainVocal")
    _assert_optional_audio_file(backup_vocal_file, "backupVocal")
    _assert_optional_audio_file(instrumental_file, "instrumental")
    _validate_unit_interval(reverb_room_size, "reverbRoomSize")
    _validate_unit_interval(reverb_wet, "reverbWetLevel")
    _validate_unit_interval(reverb_dry, "reverbDryLevel")
    _validate_unit_interval(reverb_damping, "reverbDamping")

    output_format = output_format.lower().strip()
    if output_format not in VALID_OUTPUT_FORMATS:
        raise InvalidMixingRequestError(
            "outputFormat must be one of %s" % sorted(VALID_OUTPUT_FORMATS)
        )

    mixing_id = f"mix_{int(time.time() * 1000)}_{uuid_lib.uuid4()}"
    cache_paths = infer_engine.get_cache_paths()
    work_dir = cache_paths["inputs"] / "mixing" / mixing_id
    input_dir = work_dir / "input"
    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        main_local = _save_upload_audio(main_vocal_file, input_dir, "main_vocal.wav")
        backup_local = _save_optional_upload_audio(backup_vocal_file, input_dir, "backup_vocal.wav")
        instrumental_local = _save_optional_upload_audio(
            instrumental_file,
            input_dir,
            "instrumental.wav",
        )

        filename_base = Path(main_local).stem
        wet_vocal_local = output_dir / f"{filename_base}_with_effects.wav"
        final_mix_local = output_dir / f"{filename_base}_Final_Cover.{output_format}"

        logger.info("[mixing] %s applying notebook effects chain", mixing_id)
        t_start = time.time()
        _add_audio_effects(
            input_path=main_local,
            output_path=wet_vocal_local,
            reverb_room_size=reverb_room_size,
            reverb_wet=reverb_wet,
            reverb_dry=reverb_dry,
            reverb_damping=reverb_damping,
        )

        logger.info("[mixing] %s overlaying vocals/background with notebook gains", mixing_id)
        mixed_audio = _combine_audio(
            main_vocal_path=wet_vocal_local,
            backup_vocal_path=backup_local,
            instrumental_path=instrumental_local,
            output_path=final_mix_local,
            main_gain=main_gain,
            backup_gain=backup_gain,
            inst_gain=inst_gain,
            output_format=output_format,
        )
        elapsed_ms = int((time.time() - t_start) * 1000)

        wet_url = _upload_output(wet_vocal_local, user_id, mixing_id, "aiVocalsWet", "wav")
        final_url = _upload_output(final_mix_local, user_id, mixing_id, "finalMix", output_format)

        result = {
            "mixingId": mixing_id,
            "pipeline": "audio_mixing_guide notebook pipeline",
            "durationMs": elapsed_ms,
            "inputFileNames": {
                "mainVocal": main_vocal_file.filename,
                "backupVocal": backup_vocal_file.filename if backup_vocal_file else None,
                "instrumental": instrumental_file.filename if instrumental_file else None,
            },
            "outputs": {
                "aiVocalsWet": _output_payload(wet_vocal_local, wet_url, "wav"),
                "finalMix": _output_payload(final_mix_local, final_url, output_format),
            },
            "audioInfo": {
                "durationMs": len(mixed_audio),
                "frameRate": mixed_audio.frame_rate,
                "channels": mixed_audio.channels,
                "sampleWidth": mixed_audio.sample_width,
            },
            "params": {
                "effects": {
                    "highpassFilter": {"enabled": True, "notebookDefault": True},
                    "compressor": {"ratio": 4, "thresholdDb": -15},
                    "reverb": {
                        "roomSize": reverb_room_size,
                        "wetLevel": reverb_wet,
                        "dryLevel": reverb_dry,
                        "damping": reverb_damping,
                    },
                },
                "gains": {
                    "mainGain": main_gain,
                    "backupGain": backup_gain,
                    "instGain": inst_gain,
                    "notebookBaseMainDb": -4,
                    "notebookBaseBackupDb": -6,
                    "notebookBaseInstrumentalDb": -7,
                },
                "outputFormat": output_format,
            },
            "stages": [
                {
                    "stage": 1,
                    "name": "add_audio_effects",
                    "effects": ["HighpassFilter", "Compressor", "Reverb"],
                    "blockSizeSeconds": 1,
                },
                {
                    "stage": 2,
                    "name": "combine_audio",
                    "overlayOrder": ["mainVocalWet", "backupVocal", "instrumental"],
                    "missingOptionalTracks": "silence with main vocal duration",
                },
            ],
        }
        if keep_local:
            result["localWorkspace"] = str(work_dir)
        return result
    except InvalidMixingRequestError:
        raise
    except Exception as exc:
        logger.exception("[mixing] %s failed", mixing_id)
        raise MixingRuntimeError(str(exc)) from exc
    finally:
        if not keep_local:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                logger.warning("Failed to delete mixing cache %s", work_dir, exc_info=True)
