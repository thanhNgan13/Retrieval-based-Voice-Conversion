"""Download default RVC infer assets (Hubert, RMVPE) from Hugging Face.

These are large (~360 MB + ~180 MB) and required at infer time. They live under
`<server_root>/assets/hubert/` and `<server_root>/assets/rmvpe/` so RVC's hardcoded
relative paths (e.g. `assets/hubert/hubert_base.pt`) resolve when cwd = server root.
"""
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests

from src.services import infer_engine

logger = logging.getLogger(__name__)


_DEFAULT_HF = "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/"
_MIRROR_HF = "https://hf-mirror.com/lj1995/VoiceConversionWebUI/resolve/main/"


def _base_url() -> str:
    if os.environ.get("RVC_HF_BASE"):
        return os.environ["RVC_HF_BASE"].rstrip("/") + "/"
    if os.environ.get("RVC_HF_MIRROR", "").lower() in ("1", "true", "yes"):
        return _MIRROR_HF
    return _DEFAULT_HF


# (relative_url, dest_subpath_under_assets, friendly_name, approx_size_mb)
_DEFAULT_ASSETS = (
    ("hubert_base.pt", "hubert/hubert_base.pt", "hubert", 360),
    ("rmvpe.pt", "rmvpe/rmvpe.pt", "rmvpe", 181),
)

_UVR5_ASSETS = (
    ("uvr5_weights/HP2_all_vocals.pth", "uvr5_weights/HP2_all_vocals.pth", "HP2_all_vocals"),
    ("uvr5_weights/HP3_all_vocals.pth", "uvr5_weights/HP3_all_vocals.pth", "HP3_all_vocals"),
    (
        "uvr5_weights/HP5_only_main_vocal.pth",
        "uvr5_weights/HP5_only_main_vocal.pth",
        "HP5_only_main_vocal",
    ),
    (
        "uvr5_weights/VR-DeEchoAggressive.pth",
        "uvr5_weights/VR-DeEchoAggressive.pth",
        "VR-DeEchoAggressive",
    ),
    (
        "uvr5_weights/VR-DeEchoDeReverb.pth",
        "uvr5_weights/VR-DeEchoDeReverb.pth",
        "VR-DeEchoDeReverb",
    ),
    (
        "uvr5_weights/VR-DeEchoNormal.pth",
        "uvr5_weights/VR-DeEchoNormal.pth",
        "VR-DeEchoNormal",
    ),
    (
        "uvr5_weights/onnx_dereverb_By_FoxJoy/vocals.onnx",
        "uvr5_weights/onnx_dereverb_By_FoxJoy/vocals.onnx",
        "onnx_dereverb_By_FoxJoy/vocals.onnx",
    ),
)


_PRETRAINED_ASSETS = tuple(
    (f"{folder}/{name}", f"{folder}/{name}", f"{folder}/{name}")
    for folder in ("pretrained", "pretrained_v2")
    for name in (
        "G32k.pth",
        "G40k.pth",
        "G48k.pth",
        "D32k.pth",
        "D40k.pth",
        "D48k.pth",
        "f0G32k.pth",
        "f0G40k.pth",
        "f0G48k.pth",
        "f0D32k.pth",
        "f0D40k.pth",
        "f0D48k.pth",
    )
)

_MUTE_FILES = (
    "logs/mute/0_gt_wavs/mute32k.wav",
    "logs/mute/0_gt_wavs/mute40k.wav",
    "logs/mute/0_gt_wavs/mute48k.wav",
    "logs/mute/1_16k_wavs/mute.wav",
    "logs/mute/2a_f0/mute.wav.npy",
    "logs/mute/2b-f0nsf/mute.wav.npy",
    "logs/mute/3_feature256/mute.npy",
    "logs/mute/3_feature768/mute.npy",
)


def _download_file(url: str, dest: Path, retries: int = 6) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err: Optional[Exception] = None
    timeout = (60, 600)  # connect, read
    sess = requests.Session()
    sess.headers.update({"User-Agent": "rvc-my-server/1.0"})

    for attempt in range(retries):
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with sess.get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
                tmp.replace(dest)
            return
        except (requests.RequestException, OSError) as e:
            last_err = e
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            wait = min(8 * (2**attempt), 120)
            logger.warning(
                "Download failed (attempt %d/%d) for %s: %s — retrying in %ds",
                attempt + 1, retries, url, e, wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"Download failed after {retries} attempts: {url}") from last_err


def _status_file(root: Path, rel_path: str, name: str) -> dict:
    path = root / rel_path
    present = path.is_file()
    return {
        "name": name,
        "present": present,
        "path": str(path),
        "sizeBytes": path.stat().st_size if present else 0,
    }


def setup_default_assets(force: bool = False) -> dict:
    """Download Hubert + RMVPE if missing (or always if `force=True`).
    Returns per-asset status."""
    assets_root: Path = infer_engine.get_assets_root()
    base = _base_url()

    items = []
    for rel_url, rel_dest, name, size_mb in _DEFAULT_ASSETS:
        dest = assets_root / rel_dest
        if dest.is_file() and not force:
            items.append({
                "name": name,
                "status": "already_present",
                "path": str(dest.relative_to(assets_root.parent)),
                "sizeBytes": dest.stat().st_size,
            })
            continue
        try:
            logger.info("Downloading %s (~%d MB) → %s", name, size_mb, dest)
            _download_file(base + rel_url, dest)
            items.append({
                "name": name,
                "status": "downloaded",
                "path": str(dest.relative_to(assets_root.parent)),
                "sizeBytes": dest.stat().st_size,
            })
        except Exception as exc:
            logger.exception("Failed to download %s", name)
            items.append({
                "name": name,
                "status": "failed",
                "error": str(exc),
            })

    return {
        "baseUrl": base,
        "assetsRoot": str(assets_root),
        "assets": items,
        "ready": all(i["status"] in ("downloaded", "already_present") for i in items),
    }


def get_assets_status() -> dict:
    """Return current presence status of default assets, without downloading."""
    assets_root: Path = infer_engine.get_assets_root()

    items = []
    all_ready = True
    for _, rel_dest, name, _ in _DEFAULT_ASSETS:
        dest = assets_root / rel_dest
        present = dest.is_file()
        all_ready = all_ready and present
        items.append({
            "name": name,
            "present": present,
            "path": str(dest.relative_to(assets_root.parent)),
            "sizeBytes": dest.stat().st_size if present else 0,
        })

    return {
        "assetsRoot": str(assets_root),
        "assets": items,
        "ready": all_ready,
    }


def setup_uvr5_assets(force: bool = False) -> dict:
    """Download UVR5 separation weights if missing."""
    assets_root: Path = infer_engine.get_assets_root()
    base = _base_url()

    items = []
    for rel_url, rel_dest, name in _UVR5_ASSETS:
        dest = assets_root / rel_dest
        if dest.is_file() and not force:
            items.append({
                "name": name,
                "status": "already_present",
                "path": str(dest.relative_to(assets_root.parent)),
                "sizeBytes": dest.stat().st_size,
            })
            continue
        try:
            logger.info("Downloading UVR5 asset %s → %s", name, dest)
            _download_file(base + rel_url, dest)
            items.append({
                "name": name,
                "status": "downloaded",
                "path": str(dest.relative_to(assets_root.parent)),
                "sizeBytes": dest.stat().st_size,
            })
        except Exception as exc:
            logger.exception("Failed to download UVR5 asset %s", name)
            items.append({
                "name": name,
                "status": "failed",
                "path": str(dest),
                "error": str(exc),
            })

    return {
        "baseUrl": base,
        "assetsRoot": str(assets_root),
        "assets": items,
        "ready": all(i["status"] in ("downloaded", "already_present") for i in items),
    }


def get_uvr5_assets_status() -> dict:
    """Return current presence status of UVR5 assets, without downloading."""
    assets_root: Path = infer_engine.get_assets_root()

    items = []
    all_ready = True
    for _, rel_dest, name in _UVR5_ASSETS:
        dest = assets_root / rel_dest
        present = dest.is_file()
        all_ready = all_ready and present
        items.append({
            "name": name,
            "present": present,
            "path": str(dest.relative_to(assets_root.parent)),
            "sizeBytes": dest.stat().st_size if present else 0,
        })

    return {
        "assetsRoot": str(assets_root),
        "assets": items,
        "ready": all_ready,
    }


def get_training_assets_status() -> dict:
    """Check every asset needed for training, without downloading."""
    server_root = infer_engine.SERVER_ROOT
    assets_root: Path = infer_engine.get_assets_root()

    infer_status = get_assets_status()
    pretrained = [
        _status_file(assets_root, rel_dest, name)
        for _, rel_dest, name in _PRETRAINED_ASSETS
    ]
    mute = [
        _status_file(server_root, rel_path, rel_path)
        for rel_path in _MUTE_FILES
    ]
    weights_dir = assets_root / "weights"

    pretrained_ready = all(item["present"] for item in pretrained)
    mute_ready = all(item["present"] for item in mute)
    weights_ready = weights_dir.is_dir()
    ready = infer_status["ready"] and pretrained_ready and mute_ready and weights_ready
    missing_mute = [
        {
            "name": item["name"],
            "path": item["path"],
        }
        for item in mute
        if not item["present"]
    ]

    return {
        "serverRoot": str(server_root),
        "assetsRoot": str(assets_root),
        "ready": ready,
        "groups": {
            "infer": infer_status["ready"],
            "pretrained": pretrained_ready,
            "mute": mute_ready,
            "weightsDir": weights_ready,
        },
        "inferAssets": infer_status["assets"],
        "pretrainedAssets": pretrained,
        "muteAssets": mute,
        "manualActions": [
            {
                "name": "logs/mute",
                "required": bool(missing_mute),
                "message": (
                    "Copy logs/mute from full RVC/rvc_standalone manually."
                    if missing_mute
                    else "No manual action required."
                ),
                "missing": missing_mute,
            }
        ],
        "directories": [
            {
                "name": "assets/weights",
                "present": weights_ready,
                "path": str(weights_dir),
            }
        ],
    }


def setup_training_assets(force: bool = False) -> dict:
    """Install every asset needed for training.

    Strategy:
    - Hubert/RMVPE: reuse setup_default_assets.
    - pretrained/pretrained_v2: download from Hugging Face or configured mirror.
    - logs/mute: check only. These templates must be copied manually from a full
      RVC checkout when missing.
    - assets/weights: create directory.
    """
    server_root = infer_engine.SERVER_ROOT
    assets_root: Path = infer_engine.get_assets_root()
    base = _base_url()

    infer_result = setup_default_assets(force=force)
    items = []

    for rel_url, rel_dest, name in _PRETRAINED_ASSETS:
        dest = assets_root / rel_dest
        if dest.is_file() and not force:
            items.append({
                "name": name,
                "status": "already_present",
                "path": str(dest),
                "sizeBytes": dest.stat().st_size,
            })
            continue

        try:
            logger.info("Downloading pretrained asset %s → %s", name, dest)
            _download_file(base + rel_url, dest)
            items.append({
                "name": name,
                "status": "downloaded",
                "path": str(dest),
                "sizeBytes": dest.stat().st_size,
            })
        except Exception as exc:
            logger.exception("Failed to install pretrained asset %s", name)
            items.append({
                "name": name,
                "status": "failed",
                "path": str(dest),
                "error": str(exc),
            })

    weights_dir = assets_root / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)

    status = get_training_assets_status()
    missing_mute = [
        {
            "name": item["name"],
            "path": item["path"],
        }
        for item in status["muteAssets"]
        if not item["present"]
    ]
    if missing_mute:
        logger.warning(
            "Missing logs/mute template files. Copy logs/mute from a full RVC "
            "checkout or rvc_standalone manually before training: %s",
            ", ".join(item["name"] for item in missing_mute),
        )

    mute_setup = {
        "status": "present" if not missing_mute else "missing_manual_copy_required",
        "message": (
            "logs/mute template is present"
            if not missing_mute
            else (
                "logs/mute is not auto-installed. Copy logs/mute from full "
                "RVC/rvc_standalone manually."
            )
        ),
        "missing": missing_mute,
    }

    return {
        "baseUrl": base,
        "serverRoot": str(server_root),
        "assetsRoot": str(assets_root),
        "inferSetup": infer_result,
        "pretrainedSetup": items,
        "muteSetup": mute_setup,
        "weightsDir": str(weights_dir),
        "ready": status["ready"],
        "status": status,
    }
