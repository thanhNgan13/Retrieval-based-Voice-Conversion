"""Singleton wrapper around RVC `VC` engine.

The `infer/`, `configs/`, `i18n/` packages live INSIDE rvc_my_server (copied from
rvc_standalone) so the server is self-contained for deployment. We just need to:
  - cwd at the server root so RVC's hardcoded relative paths
    (`assets/hubert/hubert_base.pt`, ...) resolve.
  - set env vars `weight_root`, `index_root`, `rmvpe_root` to point at our cache /
    assets folders.

Loading PyTorch model + Hubert + RMVPE takes seconds, so we initialize once on
the first inference call and reuse across requests. All access is serialized
through a single lock — concurrent inference on the same VC instance is not safe.
"""
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional

from src.config.settings import settings

logger = logging.getLogger(__name__)


# rvc_my_server/ (= server root) — sibling of src/, configs/, infer/, i18n/.
SERVER_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# RLock (reentrant) — service holds it across the whole infer flow, then calls
# get_engine() which acquires it AGAIN for lazy-init safety. A plain Lock would
# self-deadlock here; RLock lets the same thread re-acquire freely.
_lock = threading.RLock()
_state: dict = {
    "vc": None,
    "config": None,
    "current_model_id": None,
    "bootstrapped": False,
    "assets_root": None,
    "cache_root": None,
}


def _bootstrap() -> None:
    if _state["bootstrapped"]:
        return

    # Resolve paths relative to ORIGINAL cwd before we chdir.
    assets_root = (Path(settings.ASSETS_DIR) if Path(settings.ASSETS_DIR).is_absolute()
                   else SERVER_ROOT / settings.ASSETS_DIR).resolve()
    cache_root = (Path(settings.INFER_CACHE_DIR) if Path(settings.INFER_CACHE_DIR).is_absolute()
                  else SERVER_ROOT / settings.INFER_CACHE_DIR).resolve()

    for sub in ("hubert", "rmvpe"):
        (assets_root / sub).mkdir(parents=True, exist_ok=True)
    for sub in ("weights", "indices", "inputs", "outputs"):
        (cache_root / sub).mkdir(parents=True, exist_ok=True)

    # RVC reads these env vars at runtime.
    os.environ["weight_root"] = str(cache_root / "weights")
    os.environ["index_root"] = str(cache_root / "indices")
    os.environ["outside_index_root"] = str(cache_root / "indices")
    os.environ["rmvpe_root"] = str(assets_root / "rmvpe")

    # cwd at SERVER_ROOT so relative 'assets/hubert/hubert_base.pt' inside RVC code works.
    os.chdir(SERVER_ROOT)

    # SERVER_ROOT should already be on sys.path (uvicorn started here), add defensively.
    str_root = str(SERVER_ROOT)
    if str_root not in sys.path:
        sys.path.insert(0, str_root)

    _state["assets_root"] = assets_root
    _state["cache_root"] = cache_root
    _state["bootstrapped"] = True
    logger.info(
        "Infer engine bootstrapped: server_root=%s, assets=%s, cache=%s",
        SERVER_ROOT,
        assets_root,
        cache_root,
    )


def get_engine():
    """Return (vc, config). Lazily initializes on first call.

    First-time setup is slow — typical timings on a clean install:
      - importing torch + fairseq + librosa + faiss + numba: 20–60s
      - constructing Config (queries CUDA): 1–5s
      - creating VC class (light, no model loaded yet): <1s
    Subsequent calls return the cached instance instantly.
    """
    import time

    with _lock:
        if _state["vc"] is None:
            logger.info(
                "Bootstrapping infer engine (FIRST CALL — heavy imports, can take 30–60s)..."
            )
            _bootstrap()

            logger.info("Importing configs.config.Config ...")
            t = time.time()
            saved_argv = sys.argv
            sys.argv = ["rvc_my_server_infer"]
            try:
                from configs.config import Config
                logger.info("  ↳ configs.config imported in %.1fs", time.time() - t)

                logger.info("Constructing Config() (querying CUDA + setting fp16/x_pad) ...")
                t = time.time()
                _state["config"] = Config()
                logger.info(
                    "  ↳ Config ready in %.1fs (device=%s, is_half=%s)",
                    time.time() - t, _state["config"].device, _state["config"].is_half,
                )
            finally:
                sys.argv = saved_argv

            logger.info(
                "Importing infer.modules.vc.modules.VC (this triggers torch/fairseq/librosa/faiss) ..."
            )
            t = time.time()
            from infer.modules.vc.modules import VC
            logger.info("  ↳ VC module imported in %.1fs", time.time() - t)

            logger.info("Creating VC engine instance ...")
            _state["vc"] = VC(_state["config"])
            logger.info(
                "VC engine ready (device=%s, is_half=%s) — no model loaded yet",
                _state["config"].device,
                _state["config"].is_half,
            )
        return _state["vc"], _state["config"]


def engine_lock() -> threading.Lock:
    return _lock


def get_current_model_id() -> Optional[str]:
    return _state.get("current_model_id")


def set_current_model_id(model_id: Optional[str]) -> None:
    _state["current_model_id"] = model_id


def get_assets_root() -> Path:
    if _state["assets_root"] is None:
        _bootstrap()
    return _state["assets_root"]


def get_cache_paths() -> dict:
    if _state["cache_root"] is None:
        _bootstrap()
    root: Path = _state["cache_root"]
    return {
        "weights": root / "weights",
        "indices": root / "indices",
        "inputs": root / "inputs",
        "outputs": root / "outputs",
    }
