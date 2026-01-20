#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Skills Sync Sanity ==="
# skills-sync might not have run.sh if it's purely documentation or managed via other means?
# Assessment said "skills-sync | run.sh: X".
# So verify SKILL.md exists.
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "  [PASS] SKILL.md exists"
else
    echo "  [FAIL] SKILL.md missing"
    exit 1
fi
echo "Result: PASS"
