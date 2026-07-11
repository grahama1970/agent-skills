#!/usr/bin/env bash
set -euo pipefail

# Supported audio e2e execution entry point.  This wrapper intentionally exposes
# only the package CLI; transcripts and fixture responses are never accepted here.
PYTHONPATH="${PYTHONPATH:-skills/embry-voice-control/src}" exec /usr/bin/python3 -m embry_voice_control.audio_e2e "$@"
