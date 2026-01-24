#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "=== Cleanup Skill Sanity ==="
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then echo "  [PASS] SKILL.md exists"; else exit 1; fi
if [[ -f "$SCRIPT_DIR/cleanup.py" ]]; then echo "  [PASS] cleanup.py exists"; else exit 1; fi
echo "Result: PASS"
