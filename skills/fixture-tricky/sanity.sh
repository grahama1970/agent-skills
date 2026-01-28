#!/usr/bin/env bash
# Sanity check for fixture-tricky skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Sanity check for fixture-tricky ==="

# Check python3 exists
if ! command -v python3 >/dev/null 2>&1; then
    echo "FAIL: python3 not found"
    exit 1
fi
echo "PASS: python3 found"

# Check main script exists
if [[ ! -f "$SCRIPT_DIR/generate.py" ]]; then
    echo "FAIL: generate.py not found"
    exit 1
fi
echo "PASS: generate.py exists"

# Check tricks directory exists
if [[ ! -d "$SCRIPT_DIR/tricks" ]]; then
    echo "FAIL: tricks/ directory not found"
    exit 1
fi
echo "PASS: tricks/ directory exists"

# Check SKILL.md exists
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi
echo "PASS: SKILL.md exists"

# Check CLI help works
if python3 "$SCRIPT_DIR/generate.py" --help >/dev/null 2>&1; then
    echo "PASS: CLI --help works"
else
    echo "WARN: CLI --help check failed (may need dependencies)"
fi

echo "=== Sanity check complete ==="
