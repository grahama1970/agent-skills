#!/bin/bash
set -euo pipefail

# Stop hook: prevent agent from stopping until PersonaPlex GOAL.md is satisfied.
# Exit 0 = allow stop. Exit 2 = force continue (stderr fed back as prompt).

if [ "${OPENCODE_HOOK_ACTIVE:-}" = "true" ]; then
  exit 0
fi
export OPENCODE_HOOK_ACTIVE=true

PROJECT_ROOT="/home/graham/workspace/experiments/agent-skills"
GOAL_FILE="$PROJECT_ROOT/skills/personaplex/GOAL.md"

if [ ! -f "$GOAL_FILE" ]; then
  exit 0
fi

# Find the latest E2E receipt
LATEST_RECEIPT=$(find /tmp -maxdepth 1 -name "personaplex-e2e-live-*" -type d 2>/dev/null | sort | tail -1)
if [ -z "$LATEST_RECEIPT" ]; then
  echo "No E2E live receipt found. Run the E2E probe first: personaplex_e2e_live_voice_session.py" >&2
  exit 2
fi

RECEIPT_FILE="$LATEST_RECEIPT/e2e-live-voice-receipt.json"
if [ ! -f "$RECEIPT_FILE" ]; then
  echo "No e2e-live-voice-receipt.json in $LATEST_RECEIPT" >&2
  exit 2
fi

ALL_REAL=$(python3 -c "
import json
d = json.load(open('$RECEIPT_FILE'))
print(d.get('all_real_true', False))
")

if [ "$ALL_REAL" != "True" ]; then
  FLAGS=$(python3 -c "
import json
d = json.load(open('$RECEIPT_FILE'))
flags = d.get('real_flags', {})
false_flags = [k for k, v in flags.items() if not v]
print(', '.join(false_flags))
")
  echo "GOAL not met. False real_* flags: $FLAGS. Continue looping until all are true." >&2
  exit 2
fi

echo "All PersonaPlex real_* flags are true. Goal met."
exit 0
