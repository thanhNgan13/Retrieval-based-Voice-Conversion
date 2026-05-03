#!/bin/sh
set -e
python3 -c "import torch; print('[RVC] PyTorch', torch.__version__); print('[RVC] CUDA available (in container):', torch.cuda.is_available())" 2>&1 || true
exec python3 infer-web.py
