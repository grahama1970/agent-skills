#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${PERSONAPLEX_E2E_OUT_DIR:-/tmp/personaplex-e2e-live-voice-ui}"
PYTHONPATH="${REPO_ROOT}/skills/personaplex/scripts:${PYTHONPATH:-}"
export PYTHONPATH

mkdir -p "${OUT_DIR}"
python3 "${REPO_ROOT}/skills/personaplex/scripts/personaplex_e2e_live_voice_session.py" \
  --out-dir "${OUT_DIR}" \
  --memory-url "${PERSONAPLEX_MEMORY_URL:-http://127.0.0.1:8601}" \
  --evidence-case-url "${PERSONAPLEX_EVIDENCE_CASE_URL:-${PERSONAPLEX_MEMORY_URL:-http://127.0.0.1:8601}}" \
  --deepgram-audio-path "${PERSONAPLEX_P8_AUDIO_PATH:-${PERSONAPLEX_ROOT:-${REPO_ROOT}}/assets/test/input_assistant.wav}" \
  --require-real

printf '\nE2E receipt: %s\n' "${OUT_DIR}/e2e-live-voice-receipt.json"
printf 'Verification UI: %s\n' "${OUT_DIR}/personaplex-e2e-live-voice-ui.html"
printf 'Serve UI: python3 -m http.server 8765 --directory %q\n' "${OUT_DIR}"
