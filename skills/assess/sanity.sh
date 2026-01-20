#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Assess Skill Sanity ==="

# Assess is primarily a methodology/documentation skill.
# Verification consists of ensuring the core SKILL.md documentation exists.

if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "  [PASS] SKILL.md exists"
else
    echo "  [FAIL] SKILL.md missing"
    exit 1
fi

echo "Result: PASS"
