#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${PERSONAPLEX_SANITY_OUT_DIR:-/tmp/personaplex-p8-p9-p10-sanity}"
MEMORY_URL="${PERSONAPLEX_MEMORY_URL:-http://127.0.0.1:8601}"
mkdir -p "$OUT_DIR"
export PYTHONPATH="$REPO_ROOT/skills/personaplex/scripts:${PYTHONPATH:-}"
ARGS=("$REPO_ROOT/skills/personaplex/scripts/personaplex_p9_compaction_probe.py" --out-dir "$OUT_DIR" --memory-url "$MEMORY_URL")
if [[ -n "${PERSONAPLEX_P8_AUDIO_PATH:-}" ]]; then
  ARGS+=(--audio-path "$PERSONAPLEX_P8_AUDIO_PATH")
fi
if [[ -n "${PERSONAPLEX_P9_TURNS_JSON:-}" ]]; then
  ARGS+=(--turns-json "$PERSONAPLEX_P9_TURNS_JSON")
fi
if [[ -n "${PERSONAPLEX_PREVIOUS_HEAD_JSON:-}" ]]; then
  ARGS+=(--previous-head-json "$PERSONAPLEX_PREVIOUS_HEAD_JSON")
fi
if [[ -n "${PERSONAPLEX_EXPECTED_PREVIOUS_GENERATION:-}" ]]; then
  ARGS+=(--expected-previous-generation "$PERSONAPLEX_EXPECTED_PREVIOUS_GENERATION")
fi
if [[ "${PERSONAPLEX_REQUIRE_REAL:-0}" == "1" ]]; then
  ARGS+=(--require-real)
fi
python3 "${ARGS[@]}"
