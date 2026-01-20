#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Code Review Sanity ==="
# "code-review | run.sh: X" in assessment.
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "  [PASS] SKILL.md exists"
else
    echo "  [FAIL] SKILL.md missing"
    exit 1
fi
echo "Result: PASS"
