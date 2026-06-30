#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${ORPHEUS_PERSONAPLEX_REFERENCE_PACK:?Set ORPHEUS_PERSONAPLEX_REFERENCE_PACK to a real Orpheus reference pack JSON}"
: "${PERSONAPLEX_ROOT:?Set PERSONAPLEX_ROOT to ${HOME}/workspace/experiments/personaplex or another PersonaPlex checkout}"
: "${PERSONAPLEX_HUMAN_INPUT_WAV:?Set PERSONAPLEX_HUMAN_INPUT_WAV to a real human input WAV for bidirectional offline evaluation}"

OUT_DIR="${PERSONAPLEX_E2E_OUT_DIR:-/mnt/storage12tb/skills/personaplex/outputs/e2e-$(date -u +%Y%m%dT%H%M%SZ)}"

exec "$SCRIPT_DIR/run.sh" verify-e2e \
  --reference-pack "$ORPHEUS_PERSONAPLEX_REFERENCE_PACK" \
  --personaplex-root "$PERSONAPLEX_ROOT" \
  --human-input-wav "$PERSONAPLEX_HUMAN_INPUT_WAV" \
  --out-dir "$OUT_DIR"
