import gc
import hashlib
import logging
import os
import queue
import re
import shutil
import threading
import time
import uuid as uuid_lib
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
import onnxruntime as ort
import soundfile as sf
import torch
from fastapi import UploadFile
from tqdm import tqdm

from src.config.firebase import get_bucket
from src.services import infer_engine
from src.utils.storage_helpers import firebase_download_url

logger = logging.getLogger(__name__)

VALID_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma"}
OUTPUT_CONTENT_TYPE = "audio/wav"

MDX_MODEL_FILES = {
    "vocal": "UVR-MDX-NET-Voc_FT.onnx",
    "karaoke": "UVR_MDXNET_KARA_2.onnx",
    "dereverb": "Reverb_HQ_By_FoxJoy.onnx",
}

STEM_NAMING = {
    "Vocals": "Instrumental",
    "Other": "Instruments",
    "Instrumental": "Vocals",
    "Drums": "Drumless",
    "Bass": "Bassless",
}

MODEL_PARAMS = {
    "77d07b2667ddf05b9e3175941b4454a0": {
        "compensate": 1.021,
        "mdx_dim_f_set": 3072,
        "mdx_dim_t_set": 8,
        "mdx_n_fft_scale_set": 7680,
        "primary_stem": "Vocals",
    },
    "1d64a6d2c30f709b8c9b4ce1366d96ee": {
        "compensate": 1.035,
        "mdx_dim_f_set": 2048,
        "mdx_dim_t_set": 8,
        "mdx_n_fft_scale_set": 5120,
        "primary_stem": "Instrumental",
    },
    "cd5b2989ad863f116c855db1dfe24e39": {
        "compensate": 1.035,
        "mdx_dim_f_set": 3072,
        "mdx_dim_t_set": 9,
        "mdx_n_fft_scale_set": 6144,
        "primary_stem": "Other",
    },
}


class InvalidSeparationRequestError(Exception):
    pass


class SeparationRuntimeError(Exception):
    pass


class MDXModel:
    def __init__(
        self,
        device,
        dim_f,
        dim_t,
        n_fft,
        hop=1024,
        stem_name=None,
        compensation=1.000,
    ):
        self.dim_f = dim_f
        self.dim_t = dim_t
        self.dim_c = 4
        self.n_fft = n_fft
        self.hop = hop
        self.stem_name = stem_name
        self.compensation = compensation

        self.n_bins = self.n_fft // 2 + 1
        self.chunk_size = hop * (self.dim_t - 1)
        self.window = torch.hann_window(window_length=self.n_fft, periodic=True).to(device)
        self.freq_pad = torch.zeros([1, 4, self.n_bins - self.dim_f, self.dim_t]).to(device)

    def stft(self, x):
        x = x.reshape([-1, self.chunk_size])
        x = torch.stft(
            x,
            n_fft=self.n_fft,
            hop_length=self.hop,
            window=self.window,
            center=True,
            return_complex=True,
        )
        x = torch.view_as_real(x)
        x = x.permute([0, 3, 1, 2])
        x = x.reshape([-1, 2, 2, self.n_bins, self.dim_t]).reshape(
            [-1, 4, self.n_bins, self.dim_t]
        )
        return x[:, :, : self.dim_f]

    def istft(self, x, freq_pad=None):
        freq_pad = self.freq_pad.repeat([x.shape[0], 1, 1, 1]) if freq_pad is None else freq_pad
        x = torch.cat([x, freq_pad], -2)
        x = x.reshape([-1, 2, 2, self.n_bins, self.dim_t]).reshape(
            [-1, 2, self.n_bins, self.dim_t]
        )
        x = x.permute([0, 2, 3, 1])
        x = x.contiguous()
        x = torch.view_as_complex(x)
        x = torch.istft(
            x,
            n_fft=self.n_fft,
            hop_length=self.hop,
            window=self.window,
            center=True,
        )
        return x.reshape([-1, 2, self.chunk_size])


class MDX:
    def __init__(self, model_path: str, params: MDXModel, providers):
        self.device = params.window.device
        self.model = params
        self.ort = ort.InferenceSession(model_path, providers=providers)
        self.ort.run(None, {"input": torch.rand(1, 4, params.dim_f, params.dim_t).numpy()})
        self.process = lambda spec: self.ort.run(None, {"input": spec.cpu().numpy()})[0]
        self.prog = None

    @staticmethod
    def get_hash(model_path):
        try:
            with open(model_path, "rb") as f:
                f.seek(-10000 * 1024, 2)
                model_hash = hashlib.md5(f.read()).hexdigest()
        except Exception:
            with open(model_path, "rb") as f:
                model_hash = hashlib.md5(f.read()).hexdigest()
        return model_hash

    @staticmethod
    def segment(wave, combine=True, chunk_size=44100 * 0, margin_size=44100 * 1):
        if combine:
            processed_wave = None
            for segment_count, segment in enumerate(wave):
                start = 0 if segment_count == 0 else margin_size
                end = None if segment_count == len(wave) - 1 else -margin_size
                if margin_size == 0:
                    end = None
                if processed_wave is None:
                    processed_wave = segment[:, start:end]
                else:
                    processed_wave = np.concatenate(
                        (processed_wave, segment[:, start:end]),
                        axis=-1,
                    )
        else:
            processed_wave = []
            sample_count = wave.shape[-1]
            if chunk_size <= 0 or chunk_size > sample_count:
                chunk_size = sample_count
            if margin_size > chunk_size:
                margin_size = chunk_size
            for segment_count, skip in enumerate(range(0, sample_count, chunk_size)):
                margin = 0 if segment_count == 0 else margin_size
                end = min(skip + chunk_size + margin_size, sample_count)
                start = skip - margin
                cut = wave[:, start:end].copy()
                processed_wave.append(cut)
                if end == sample_count:
                    break
        return processed_wave

    def pad_wave(self, wave):
        n_sample = wave.shape[1]
        trim = self.model.n_fft // 2
        gen_size = self.model.chunk_size - 2 * trim
        pad = gen_size - n_sample % gen_size
        wave_p = np.concatenate(
            (np.zeros((2, trim)), wave, np.zeros((2, pad)), np.zeros((2, trim))),
            1,
        )
        mix_waves = []
        for i in range(0, n_sample + pad, gen_size):
            waves = np.array(wave_p[:, i : i + self.model.chunk_size])
            mix_waves.append(waves)
        mix_waves = torch.tensor(mix_waves, dtype=torch.float32).to(self.device)
        return mix_waves, pad, trim

    def _process_wave(self, mix_waves, trim, pad, q: queue.Queue, err_q: queue.Queue, _id: int):
        try:
            mix_waves = mix_waves.split(1)
            with torch.no_grad():
                pw = []
                for mix_wave in mix_waves:
                    self.prog.update()
                    spec = self.model.stft(mix_wave)
                    processed_spec = torch.tensor(self.process(spec))
                    processed_wav = self.model.istft(processed_spec.to(self.device))
                    processed_wav = (
                        processed_wav[:, :, trim:-trim]
                        .transpose(0, 1)
                        .reshape(2, -1)
                        .cpu()
                        .numpy()
                    )
                    pw.append(processed_wav)
            processed_signal = np.concatenate(pw, axis=-1)
            if pad:
                processed_signal = processed_signal[:, :-pad]
            q.put({_id: processed_signal})
        except Exception as exc:
            err_q.put(exc)

    def process_wave(self, wave: np.array, mt_threads=1):
        self.prog = tqdm(total=0, disable=True)
        chunk = wave.shape[-1] // mt_threads
        waves = self.segment(wave, False, chunk)
        q = queue.Queue()
        err_q = queue.Queue()
        threads = []
        for c, batch in enumerate(waves):
            mix_waves, pad, trim = self.pad_wave(batch)
            self.prog.total = len(mix_waves) * mt_threads
            thread = threading.Thread(
                target=self._process_wave,
                args=(mix_waves, trim, pad, q, err_q, c),
            )
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join()
        self.prog.close()
        if not err_q.empty():
            raise err_q.get()

        processed_batches = []
        while not q.empty():
            processed_batches.append(q.get())
        processed_batches = [
            list(wave.values())[0]
            for wave in sorted(processed_batches, key=lambda d: list(d.keys())[0])
        ]
        return self.segment(processed_batches, True, chunk)


def mdx_models_dir() -> Path:
    return infer_engine.SERVER_ROOT / "mdxnet_models"


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


def _onnx_providers() -> list[str]:
    if torch.cuda.is_available():
        available = set(ort.get_available_providers())
        if "CUDAExecutionProvider" in available:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def _assert_mdx_models_available() -> dict[str, Path]:
    root = mdx_models_dir()
    paths = {key: root / name for key, name in MDX_MODEL_FILES.items()}
    missing = [path.name for path in paths.values() if not path.is_file()]
    if missing:
        raise InvalidSeparationRequestError(
            "Missing MDX-Net model(s): %s. Call admin /setup-mdxnet-assets first."
            % ", ".join(missing)
        )
    return paths


def list_mdx_models() -> dict:
    root = mdx_models_dir()
    models = []
    for key, filename in MDX_MODEL_FILES.items():
        path = root / filename
        models.append(
            {
                "key": key,
                "fileName": filename,
                "present": path.is_file(),
                "path": str(path),
                "sizeBytes": path.stat().st_size if path.is_file() else 0,
            }
        )
    return {
        "modelDir": str(root),
        "pipeline": "MDX-Net 3-stage notebook pipeline",
        "ready": all(item["present"] for item in models),
        "models": models,
    }


def _convert_to_stereo_pure_python(audio_path: str) -> str:
    wave, sr = librosa.load(audio_path, mono=False, sr=44100)
    if wave.ndim == 1:
        stereo_path = f"{os.path.splitext(audio_path)[0]}_stereo.wav"
        wave_stereo = np.stack([wave, wave], axis=0)
        sf.write(stereo_path, wave_stereo.T, sr)
        return stereo_path
    return audio_path


def _run_mdx_standalone(
    output_dir,
    model_path,
    filename,
    providers,
    exclude_main=False,
    exclude_inversion=False,
    suffix=None,
    invert_suffix=None,
    denoise=False,
):
    device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")

    m_threads = 1
    if torch.cuda.is_available():
        device_properties = torch.cuda.get_device_properties(device)
        vram_gb = device_properties.total_memory / 1024**3
        m_threads = 1 if vram_gb < 8 else 2

    model_hash = MDX.get_hash(model_path)
    mp = MODEL_PARAMS.get(model_hash)
    if mp is None:
        raise ValueError(
            "No MDX-Net params configured for model hash %s. Check that the ONNX file "
            "matches audio_separation_guide.ipynb." % model_hash
        )

    model = MDXModel(
        device,
        dim_f=mp["mdx_dim_f_set"],
        dim_t=2 ** mp["mdx_dim_t_set"],
        n_fft=mp["mdx_n_fft_scale_set"],
        stem_name=mp["primary_stem"],
        compensation=mp["compensate"],
    )

    mdx_sess = MDX(str(model_path), model, providers=providers)

    input_file = _convert_to_stereo_pure_python(str(filename))
    wave, sr = librosa.load(input_file, mono=False, sr=44100)
    if wave.ndim == 1:
        wave = np.stack([wave, wave], axis=0)

    peak = max(np.max(wave), abs(np.min(wave)))
    if peak > 0:
        wave /= peak

    if denoise:
        wave_processed = -(mdx_sess.process_wave(-wave, m_threads)) + (
            mdx_sess.process_wave(wave, m_threads)
        )
        wave_processed *= 0.5
    else:
        wave_processed = mdx_sess.process_wave(wave, m_threads)

    wave_processed *= peak
    stem_name = model.stem_name if suffix is None else suffix

    os.makedirs(output_dir, exist_ok=True)

    main_filepath = None
    if not exclude_main:
        main_filepath = os.path.join(
            output_dir,
            f"{os.path.basename(os.path.splitext(str(filename))[0])}_{stem_name}.wav",
        )
        sf.write(main_filepath, wave_processed.T, sr)

    invert_filepath = None
    if not exclude_inversion:
        diff_stem_name = STEM_NAMING.get(stem_name) if invert_suffix is None else invert_suffix
        stem_name = f"{stem_name}_diff" if diff_stem_name is None else diff_stem_name
        invert_filepath = os.path.join(
            output_dir,
            f"{os.path.basename(os.path.splitext(str(filename))[0])}_{stem_name}.wav",
        )
        sf.write(invert_filepath, (-wave_processed.T * model.compensation) + wave.T, sr)

    del mdx_sess, wave_processed, wave
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return main_filepath, invert_filepath


def _upload_output(local_path: Path, user_id: str, separation_id: str, stem: str) -> str:
    object_path = f"separation_outputs/{user_id}/{separation_id}/{stem}.wav"
    bucket = get_bucket()
    blob = bucket.blob(object_path)
    token = str(uuid_lib.uuid4())
    blob.metadata = {"firebaseStorageDownloadTokens": token}
    blob.upload_from_filename(str(local_path), content_type=OUTPUT_CONTENT_TYPE)
    return firebase_download_url(bucket.name, object_path, token)


def _output_payload(local_path: Path, url: str) -> dict:
    return {
        "url": url,
        "fileName": local_path.name,
        "sizeBytes": local_path.stat().st_size,
    }


def separate_song(
    audio_file: UploadFile,
    user_id: str,
    keep_local: bool = False,
) -> dict:
    _assert_audio_file(audio_file)

    model_paths = _assert_mdx_models_available()
    separation_id = f"sep_{int(time.time() * 1000)}_{uuid_lib.uuid4()}"
    cache_paths = infer_engine.get_cache_paths()
    work_dir = cache_paths["inputs"] / "separation" / separation_id
    input_dir = work_dir / "input"
    output_dir = work_dir / "output"
    local_input: Optional[Path] = None

    try:
        local_input = _save_upload_audio(audio_file, input_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        providers = _onnx_providers()

        logger.info(
            "[separation] %s running MDX-Net notebook pipeline providers=%s",
            separation_id,
            providers,
        )
        t_start = time.time()
        with infer_engine.engine_lock():
            vocals_path, instrumental_path = _run_mdx_standalone(
                output_dir=str(output_dir),
                model_path=model_paths["vocal"],
                filename=str(local_input),
                providers=providers,
                denoise=True,
            )

            backup_vocals_path, main_vocals_path = _run_mdx_standalone(
                output_dir=str(output_dir),
                model_path=model_paths["karaoke"],
                filename=vocals_path,
                providers=providers,
                suffix="Backup",
                invert_suffix="Main",
                denoise=True,
            )
            if vocals_path and os.path.exists(vocals_path):
                os.remove(vocals_path)

            _, main_vocals_dereverb_path = _run_mdx_standalone(
                output_dir=str(output_dir),
                model_path=model_paths["dereverb"],
                filename=main_vocals_path,
                providers=providers,
                invert_suffix="DeReverb",
                exclude_main=True,
                denoise=True,
            )
            if main_vocals_path and os.path.exists(main_vocals_path):
                os.remove(main_vocals_path)

        elapsed_ms = int((time.time() - t_start) * 1000)
        outputs = {
            "instrumental": Path(instrumental_path),
            "backupVocals": Path(backup_vocals_path),
            "mainVocalsDereverb": Path(main_vocals_dereverb_path),
        }

        logger.info("[separation] %s uploading MDX-Net outputs", separation_id)
        urls = {
            key: _upload_output(path, user_id, separation_id, key)
            for key, path in outputs.items()
        }

        result = {
            "separationId": separation_id,
            "pipeline": "MDX-Net 3-stage notebook pipeline",
            "providers": providers,
            "outputFormat": "wav",
            "durationMs": elapsed_ms,
            "inputFileName": audio_file.filename,
            "outputs": {
                key: _output_payload(path, urls[key])
                for key, path in outputs.items()
            },
            "stages": [
                {
                    "stage": 1,
                    "model": MDX_MODEL_FILES["vocal"],
                    "outputs": ["instrumental", "temporaryVocals"],
                    "denoise": True,
                },
                {
                    "stage": 2,
                    "model": MDX_MODEL_FILES["karaoke"],
                    "outputs": ["backupVocals", "temporaryMainVocals"],
                    "denoise": True,
                },
                {
                    "stage": 3,
                    "model": MDX_MODEL_FILES["dereverb"],
                    "outputs": ["mainVocalsDereverb"],
                    "denoise": True,
                },
            ],
        }
        if keep_local:
            result["localWorkspace"] = str(work_dir)
        return result
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
