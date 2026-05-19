"""System / runtime diagnostics: verify torch installation + GPU availability."""
import logging
import platform
import re
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def _nvidia_smi_driver_cuda() -> Optional[dict]:
    """Best-effort: extract driver + CUDA version from nvidia-smi.
    Returns None if the tool isn't on PATH or the call fails.
    """
    try:
        out = subprocess.check_output(
            ["nvidia-smi"], stderr=subprocess.STDOUT, text=True, timeout=5
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    driver = None
    cuda = None
    m = re.search(r"Driver Version:\s+(\S+)", out)
    if m:
        driver = m.group(1)
    m = re.search(r"CUDA Version:\s+(\d+\.\d+)", out)
    if m:
        cuda = m.group(1)

    return {"driverVersion": driver, "cudaVersion": cuda}


def _torch_gpu_smoke_test() -> dict:
    """Allocate a tiny tensor on CUDA and run an op — fails fast if CUDA is broken."""
    import torch  # type: ignore

    try:
        t = torch.zeros(1024, device="cuda")
        s = (t + 1).sum().item()
        return {"ok": True, "sample": float(s)}
    except Exception as exc:
        logger.warning("GPU smoke test failed: %s", exc, exc_info=True)
        return {"ok": False, "error": str(exc)}


def get_torch_status() -> dict:
    """Return a snapshot of: torch install, CUDA availability, GPU info, engine state."""
    info: dict = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "nvidiaSmi": _nvidia_smi_driver_cuda(),
    }

    try:
        import torch  # type: ignore
    except ImportError as exc:
        info["torch"] = {"installed": False, "error": str(exc)}
        info["ready"] = False
        return info

    cuda_available = bool(torch.cuda.is_available())
    torch_info: dict = {
        "installed": True,
        "version": torch.__version__,
        "cudaBuild": getattr(torch.version, "cuda", None),
        "cudnnVersion": (
            torch.backends.cudnn.version()
            if hasattr(torch.backends, "cudnn") and torch.backends.cudnn.is_available()
            else None
        ),
        "cudaAvailable": cuda_available,
        "deviceCount": int(torch.cuda.device_count()) if cuda_available else 0,
    }

    if cuda_available:
        devices = []
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            devices.append(
                {
                    "index": i,
                    "name": torch.cuda.get_device_name(i),
                    "totalMemoryBytes": int(props.total_memory),
                    "totalMemoryGb": round(props.total_memory / (1024**3), 2),
                    "computeCapability": f"{props.major}.{props.minor}",
                }
            )
        torch_info["devices"] = devices
        torch_info["smokeTest"] = _torch_gpu_smoke_test()

    info["torch"] = torch_info

    # Engine state — read-only, do NOT trigger lazy init.
    try:
        from src.services import infer_engine

        # Internal access kept narrow to avoid forcing bootstrap.
        engine_state = infer_engine._state
        config = engine_state.get("config")
        info["engine"] = {
            "bootstrapped": bool(engine_state.get("bootstrapped")),
            "device": str(config.device) if config is not None else None,
            "isHalf": getattr(config, "is_half", None) if config is not None else None,
            "currentModelId": engine_state.get("current_model_id"),
        }
    except Exception as exc:
        info["engine"] = {"error": str(exc)}

    info["ready"] = bool(torch_info.get("installed"))
    return info
