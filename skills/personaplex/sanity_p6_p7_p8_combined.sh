#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${OUT_DIR:-/tmp/personaplex-p6-p7-p8-sanity}"
MEMORY_URL="${PERSONAPLEX_MEMORY_URL:-${MEMORY_URL:-http://127.0.0.1:8601}}"
EVIDENCE_CASE_URL="${PERSONAPLEX_EVIDENCE_CASE_URL:-${EVIDENCE_CASE_URL:-http://127.0.0.1:8601}}"
DEEPGRAM_URL="${PERSONAPLEX_DEEPGRAM_URL:-${DEEPGRAM_URL:-}}"
AUDIO_PATH="${PERSONAPLEX_P8_AUDIO_PATH:-}"
REQUIRE_ARGS=()
if [[ "${PERSONAPLEX_REQUIRE_REAL:-0}" == "1" ]]; then
  REQUIRE_ARGS+=(--require-real)
fi
if [[ -z "${DEEPGRAM_API_KEY:-}" && -f "$HOME/.zshrc" && -x "$(command -v zsh || true)" ]]; then
  ZSH_KEY="$(zsh -ic 'print -r -- ${DEEPGRAM_API_KEY:-}' 2>/dev/null || true)"
  if [[ -n "$ZSH_KEY" ]]; then
    export DEEPGRAM_API_KEY="$ZSH_KEY"
  fi
fi
mkdir -p "$OUT_DIR"
ARGS=(--out-dir "$OUT_DIR" --memory-url "$MEMORY_URL" --evidence-case-url "$EVIDENCE_CASE_URL")
if [[ -n "$DEEPGRAM_URL" ]]; then
  ARGS+=(--deepgram-url "$DEEPGRAM_URL")
fi
if [[ -n "$AUDIO_PATH" ]]; then
  ARGS+=(--deepgram-audio-path "$AUDIO_PATH")
fi
PYTHONPATH="$ROOT/skills/personaplex/scripts:${PYTHONPATH:-}" \
python3 "$ROOT/skills/personaplex/scripts/personaplex_p3_p5_combined_probe.py" \
  "${ARGS[@]}" \
  "${REQUIRE_ARGS[@]}"
