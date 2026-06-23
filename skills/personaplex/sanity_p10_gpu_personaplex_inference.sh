#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${PERSONAPLEX_SANITY_OUT_DIR:-/tmp/personaplex-p8-p9-p10-sanity}"
mkdir -p "$OUT_DIR"
export PYTHONPATH="$REPO_ROOT/skills/personaplex/scripts:${PYTHONPATH:-}"
ARGS=("$REPO_ROOT/skills/personaplex/scripts/personaplex_p10_gpu_inference_probe.py" --out-dir "$OUT_DIR")
if [[ -n "${PERSONAPLEX_GOLDEN_STATE_SERVER:-}" ]]; then
  ARGS+=(--server-path "$PERSONAPLEX_GOLDEN_STATE_SERVER")
fi
if [[ -n "${PERSONAPLEX_ROOT:-}" ]]; then
  ARGS+=(--personaplex-root "$PERSONAPLEX_ROOT")
fi
if [[ -n "${PERSONAPLEX_P10_COMMAND:-}" ]]; then
  ARGS+=(--command "$PERSONAPLEX_P10_COMMAND")
fi
if [[ -n "${PERSONAPLEX_P10_TIMEOUT:-}" ]]; then
  ARGS+=(--timeout "$PERSONAPLEX_P10_TIMEOUT")
fi
if [[ "${PERSONAPLEX_REQUIRE_REAL:-0}" == "1" ]]; then
  ARGS+=(--require-real)
fi
python3 "${ARGS[@]}"
