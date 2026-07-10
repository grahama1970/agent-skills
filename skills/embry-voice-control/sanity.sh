#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$SKILL_DIR/tests/test_event_journal.py" ]]; then
  uv run --project "$SKILL_DIR" pytest "$SKILL_DIR/tests/test_event_journal.py" -q
fi
bash -n "$SKILL_DIR/run.sh"
PYTHONPATH="$SKILL_DIR/src" uv run --project "$SKILL_DIR" python -m embry_voice_control.cli --help >/dev/null

echo "embry-voice-control sanity: PASS"
