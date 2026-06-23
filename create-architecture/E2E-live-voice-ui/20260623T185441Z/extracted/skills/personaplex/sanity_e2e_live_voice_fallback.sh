#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${PERSONAPLEX_E2E_FALLBACK_OUT_DIR:-/tmp/personaplex-e2e-live-voice-ui-fallback}"
PYTHONPATH="${REPO_ROOT}/skills/personaplex/scripts:${PYTHONPATH:-}"
export PYTHONPATH

rm -rf "${OUT_DIR}"
mkdir -p "${OUT_DIR}"
python3 "${REPO_ROOT}/skills/personaplex/scripts/personaplex_e2e_live_voice_session.py" \
  --out-dir "${OUT_DIR}" \
  --memory-url "http://127.0.0.1:9" \
  --evidence-case-url "http://127.0.0.1:9" \
  --skip-deepgram \
  --skip-gpu \
  --timeout 0.05 \
  --deepgram-timeout 0.05 \
  --gpu-timeout 0.05

python3 - <<'PY' "${OUT_DIR}/e2e-live-voice-receipt.json"
import json, sys
receipt = json.load(open(sys.argv[1], encoding='utf-8'))
assert receipt['all_real_true'] is False
assert receipt['real_flags']['real_deepgram'] is False
assert receipt['real_flags']['real_gpu_personaplex'] is False
assert receipt['real_flags']['real_turn_gate'] is True
assert receipt['real_flags']['real_memory_intent'] is True
print('fallback receipt is honest: all_real_true=false')
PY

printf '\nFallback receipt: %s\n' "${OUT_DIR}/e2e-live-voice-receipt.json"
printf 'Fallback UI: %s\n' "${OUT_DIR}/personaplex-e2e-live-voice-ui.html"
