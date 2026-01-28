#!/usr/bin/env bash
# Sanity check for handoff skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Sanity check for handoff ==="

# Check python3 exists
if ! command -v python3 >/dev/null 2>&1; then
    echo "FAIL: python3 not found"
    exit 1
fi
echo "PASS: python3 found"

# Check main script exists
if [[ ! -f "$SCRIPT_DIR/handoff.py" ]]; then
    echo "FAIL: handoff.py not found"
    exit 1
fi
echo "PASS: handoff.py exists"

# Check run.sh exists
if [[ ! -f "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not found"
    exit 1
fi
echo "PASS: run.sh exists"

# Check SKILL.md exists
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi
echo "PASS: SKILL.md exists"

# Check CLI help works
if python3 "$SCRIPT_DIR/handoff.py" --help >/dev/null 2>&1; then
    echo "PASS: CLI --help works"
else
    echo "WARN: CLI --help check failed (may need dependencies)"
fi

echo "=== Sanity check complete ==="
