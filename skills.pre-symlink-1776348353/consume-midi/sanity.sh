#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== consume-midi sanity ==="
[[ -f "$SCRIPT_DIR/SKILL.md" ]] && echo "  SKILL.md: PASS" || { echo "  SKILL.md: FAIL"; exit 1; }
[[ -x "$SCRIPT_DIR/run.sh" ]] && echo "  run.sh: PASS" || { echo "  run.sh: FAIL"; exit 1; }
grep -q "triggers:" "$SCRIPT_DIR/SKILL.md" && echo "  triggers: PASS" || { echo "  triggers: FAIL"; exit 1; }
echo "=== 0 errors ==="
