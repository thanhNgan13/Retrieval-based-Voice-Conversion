"""Smart dependency installer for rvc_my_server.

Detects NVIDIA GPU via `nvidia-smi`, picks the matching PyTorch CUDA wheel, then
installs the rest of `requirements.txt`. Falls back to CPU-only PyTorch when no
GPU is detected.

Usage (PowerShell / bash):
    python -m pip install -U "pip>=23.2,<24.1"   # fairseq needs older pip
    python install_deps.py

Flags:
    --cpu          Force CPU-only PyTorch even if a GPU is detected
    --cuda <ver>   Force a specific CUDA wheel (one of: 11.8, 12.1, 12.4)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from typing import Optional


# Map "supported CUDA toolkit" → PyTorch wheel suffix.
# PyTorch publishes: cu118, cu121, cu124 (as of 2026).
_TORCH_INDEX = {
    "11.8": "https://download.pytorch.org/whl/cu118",
    "12.1": "https://download.pytorch.org/whl/cu121",
    "12.4": "https://download.pytorch.org/whl/cu124",
}


def detect_cuda_version() -> Optional[str]:
    """Return CUDA version string (e.g. '12.4') from nvidia-smi, or None."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi"], stderr=subprocess.STDOUT, text=True, timeout=10
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    m = re.search(r"CUDA Version:\s+(\d+)\.(\d+)", out)
    if not m:
        return None
    return f"{m.group(1)}.{m.group(2)}"


def pick_torch_index(driver_cuda: str) -> str:
    """Pick the highest PyTorch CUDA wheel that the driver can run."""
    major, minor = (int(x) for x in driver_cuda.split("."))
    # Driver is backward-compatible: a CUDA 12.4 driver can run cu121, cu118.
    candidates = []
    for ver, url in _TORCH_INDEX.items():
        cmaj, cmin = (int(x) for x in ver.split("."))
        if (cmaj, cmin) <= (major, minor):
            candidates.append(((cmaj, cmin), url))
    if not candidates:
        # Driver too old → fall back to oldest available (cu118).
        return _TORCH_INDEX["11.8"]
    candidates.sort(reverse=True)
    return candidates[0][1]


def pip_install(args: list[str]) -> None:
    cmd = [sys.executable, "-m", "pip", "install", *args]
    print(">>>", " ".join(cmd))
    subprocess.check_call(cmd)


def verify_torch() -> None:
    code = (
        "import torch;"
        "print('torch version:', torch.__version__);"
        "print('CUDA available:', torch.cuda.is_available());"
        "print('CUDA build:', torch.version.cuda);"
        "print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
    )
    subprocess.run([sys.executable, "-c", code], check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install rvc_my_server deps with GPU autodetect.")
    parser.add_argument("--cpu", action="store_true", help="Force CPU-only PyTorch.")
    parser.add_argument("--cuda", default=None, help="Force CUDA wheel: 11.8 / 12.1 / 12.4.")
    args = parser.parse_args()

    print("=== Step 1: PyTorch ===")
    if args.cpu:
        print("Mode: --cpu → installing CPU-only PyTorch")
        pip_install(["torch", "torchvision", "torchaudio"])
    elif args.cuda:
        if args.cuda not in _TORCH_INDEX:
            print(f"--cuda must be one of {sorted(_TORCH_INDEX)}")
            return 2
        index = _TORCH_INDEX[args.cuda]
        print(f"Mode: --cuda {args.cuda} → installing PyTorch from {index}")
        pip_install(["torch", "torchvision", "torchaudio", "--index-url", index])
    else:
        detected = detect_cuda_version()
        if detected:
            index = pick_torch_index(detected)
            print(f"Detected NVIDIA GPU (CUDA {detected}) → installing PyTorch from {index}")
            pip_install(["torch", "torchvision", "torchaudio", "--index-url", index])
        else:
            print("No NVIDIA GPU detected (nvidia-smi missing or failed) → installing CPU-only PyTorch")
            print("  Tip: use --cuda 12.4 to force GPU install if you know the toolkit version.")
            pip_install(["torch", "torchvision", "torchaudio"])

    print("\n=== Step 2: requirements.txt (rest of deps) ===")
    # `torch`/`torchvision`/`torchaudio` already installed → pip will skip them.
    pip_install(["-r", "requirements.txt"])

    print("\n=== Step 3: Verification ===")
    verify_torch()
    print("\nDone. If `CUDA available: True`, GPU inference is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
