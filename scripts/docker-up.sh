#!/usr/bin/env bash
# Auto-select GPU or CPU Docker Compose: uses NVIDIA if nvidia-smi works on the host.
# Env: RVC_DOCKER_MODE=auto|cpu|gpu  (default: auto)
#      RVC_FORCE_CPU=1 or RVC_FORCE_GPU=1  (overrides)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_BASE=(docker compose -f docker-compose.yml)
COMPOSE_GPU=(docker compose -f docker-compose.yml -f docker-compose.gpu.yml)
MODE="${RVC_DOCKER_MODE:-auto}"

if [[ -n "${RVC_FORCE_CPU:-}" && "$RVC_FORCE_CPU" == "1" ]]; then
  MODE="cpu"
fi
if [[ -n "${RVC_FORCE_GPU:-}" && "$RVC_FORCE_GPU" == "1" ]]; then
  MODE="gpu"
fi

case "$MODE" in
  cpu)
    echo "[RVC] Docker: forced CPU (no GPU pass-through from compose)"
    "${COMPOSE_BASE[@]}" up --build "$@"
    ;;
  gpu)
    echo "[RVC] Docker: forced GPU (docker-compose.gpu.yml)"
    "${COMPOSE_GPU[@]}" up --build "$@"
    ;;
  auto|*)
    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
      echo "[RVC] Docker: host NVIDIA driver detected (nvidia-smi) — using GPU compose file"
      echo "[RVC] If the container still shows CUDA: False, install/configure NVIDIA Container Toolkit for Docker."
      "${COMPOSE_GPU[@]}" up --build "$@"
    else
      echo "[RVC] Docker: no usable nvidia-smi on host — using CPU (no --gpus)"
      echo "[RVC] To override: RVC_DOCKER_MODE=gpu $0"
      "${COMPOSE_BASE[@]}" up --build "$@"
    fi
    ;;
esac
