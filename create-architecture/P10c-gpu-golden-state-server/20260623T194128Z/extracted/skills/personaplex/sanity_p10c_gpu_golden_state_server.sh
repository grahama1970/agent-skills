#!/usr/bin/env bash
set -euo pipefail
python skills/personaplex/scripts/personaplex_gpu_inference_probe.py \
  --personaplex-root /home/graham/workspace/experiments/personaplex \
  --venv-python /home/graham/workspace/experiments/personaplex/.venv/bin/python \
  --golden-state-server /home/graham/workspace/experiments/personaplex/personaplex_golden_state_server.py \
  --out-dir artifacts/personaplex_sanity/p10c \
  --require-real \
  --print-json
