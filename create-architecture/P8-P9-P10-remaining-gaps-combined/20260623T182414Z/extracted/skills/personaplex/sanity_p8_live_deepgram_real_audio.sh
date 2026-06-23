#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${PERSONAPLEX_SANITY_OUT_DIR:-/tmp/personaplex-p8-p9-p10-sanity}"
mkdir -p "$OUT_DIR"
export PYTHONPATH="$REPO_ROOT/skills/personaplex/scripts:${PYTHONPATH:-}"
ARGS=("$REPO_ROOT/skills/personaplex/scripts/personaplex_p8_live_deepgram_probe.py" --out-dir "$OUT_DIR")
if [[ -n "${PERSONAPLEX_P8_AUDIO_PATH:-}" ]]; then
  ARGS+=(--audio-path "$PERSONAPLEX_P8_AUDIO_PATH")
fi
if [[ -n "${PERSONAPLEX_DEEPGRAM_URL:-}" ]]; then
  ARGS+=(--deepgram-url "$PERSONAPLEX_DEEPGRAM_URL")
fi
if [[ -n "${PERSONAPLEX_DEEPGRAM_TIMEOUT:-}" ]]; then
  ARGS+=(--timeout "$PERSONAPLEX_DEEPGRAM_TIMEOUT")
fi
if [[ "${PERSONAPLEX_REQUIRE_REAL:-0}" == "1" ]]; then
  ARGS+=(--require-real)
fi
python3 "${ARGS[@]}"
