# syntax=docker/dockerfile:1.6
#
# RVC My Server — CUDA-enabled image for FastAPI (api) and Celery worker (worker).
# The same image runs both services; docker-compose overrides the `command`.
#
# Image size: ~9-10 GB. First build ~20-40 min. Subsequent builds use layer cache.
# Build:   docker build -t rvc-my-server:gpu .
# Or:      docker compose build
#
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=0 \
    TZ=Asia/Ho_Chi_Minh

WORKDIR /app

# ---------------------------------------------------------------------------
# System packages
# ---------------------------------------------------------------------------
# - python3.10 / python3-dev / build-essential: native deps (numba, faiss, ...).
# - ffmpeg: RVC `load_audio` shells out to ffmpeg.
# - libsndfile1: soundfile backend.
# - git + curl: occasional pip fallback to git repos.
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-venv python3-pip python3-dev \
        build-essential \
        ffmpeg libsndfile1 \
        git curl ca-certificates \
        tzdata \
    && ln -sf /usr/bin/python3.10 /usr/local/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/local/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

# fairseq 0.12.2 needs pip < 24.1 (omegaconf metadata).
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade "pip>=23.2,<24.1" "setuptools<81" wheel

# ---------------------------------------------------------------------------
# PyTorch GPU (CUDA 12.4) — installed BEFORE requirements.txt so the matching
# wheel is in place when fairseq's torch dep is resolved.
# ---------------------------------------------------------------------------
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url https://download.pytorch.org/whl/cu124 \
        torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0

# ---------------------------------------------------------------------------
# App requirements — copied separately so this layer caches when only code
# changes downstream. requirements.txt deliberately omits torch/torchvision/
# torchaudio (see comment in that file).
# ---------------------------------------------------------------------------
COPY requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /app/requirements.txt

# ---------------------------------------------------------------------------
# Application code. Everything in .dockerignore is excluded.
# ---------------------------------------------------------------------------
COPY . /app

# Pre-create writable subdirs so a fresh container without volumes still boots.
RUN mkdir -p /app/assets/hubert /app/assets/rmvpe /app/cache/weights \
             /app/cache/indices /app/cache/inputs /app/cache/outputs \
             /app/cache/train_jobs

EXPOSE 8000

# Default command = API server. The worker overrides via docker-compose.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
