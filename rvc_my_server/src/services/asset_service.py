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
