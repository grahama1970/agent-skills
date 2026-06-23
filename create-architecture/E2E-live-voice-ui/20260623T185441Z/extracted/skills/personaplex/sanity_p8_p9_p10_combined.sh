#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${PERSONAPLEX_SANITY_OUT_DIR:-/tmp/personaplex-p8-p9-p10-sanity}"
MEMORY_URL="${PERSONAPLEX_MEMORY_URL:-http://127.0.0.1:8601}"
EVIDENCE_CASE_URL="${PERSONAPLEX_EVIDENCE_CASE_URL:-http://127.0.0.1:8601}"
mkdir -p "$OUT_DIR"
export PYTHONPATH="$REPO_ROOT/skills/personaplex/scripts:${PYTHONPATH:-}"
ARGS=("$REPO_ROOT/skills/personaplex/scripts/personaplex_p3_p5_combined_probe.py" --out-dir "$OUT_DIR" --memory-url "$MEMORY_URL" --evidence-case-url "$EVIDENCE_CASE_URL")
if [[ -n "${PERSONAPLEX_P8_AUDIO_PATH:-}" ]]; then
  ARGS+=(--deepgram-audio-path "$PERSONAPLEX_P8_AUDIO_PATH")
fi
if [[ -n "${PERSONAPLEX_DEEPGRAM_URL:-}" ]]; then
  ARGS+=(--deepgram-url "$PERSONAPLEX_DEEPGRAM_URL")
fi
if [[ -n "${PERSONAPLEX_GOLDEN_STATE_SERVER:-}" ]]; then
  ARGS+=(--p10-server-path "$PERSONAPLEX_GOLDEN_STATE_SERVER")
fi
if [[ -n "${PERSONAPLEX_ROOT:-}" ]]; then
  ARGS+=(--personaplex-root "$PERSONAPLEX_ROOT")
fi
if [[ -n "${PERSONAPLEX_P10_COMMAND:-}" ]]; then
  ARGS+=(--p10-command "$PERSONAPLEX_P10_COMMAND")
fi
if [[ "${PERSONAPLEX_SKIP_DEEPGRAM:-0}" == "1" ]]; then
  ARGS+=(--skip-deepgram)
fi
if [[ "${PERSONAPLEX_SKIP_GPU:-0}" == "1" ]]; then
  ARGS+=(--skip-gpu)
fi
if [[ "${PERSONAPLEX_REQUIRE_REAL:-0}" == "1" ]]; then
  ARGS+=(--require-real)
fi
python3 "${ARGS[@]}"
