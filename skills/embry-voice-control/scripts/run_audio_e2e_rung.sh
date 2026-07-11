#!/usr/bin/env bash
set -euo pipefail

# Supported audio E2E execution entry point. Transcripts and fixture responses
# are never accepted here.
SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${SKILL_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec /usr/bin/python3 -m embry_voice_control.audio_e2e "$@"
