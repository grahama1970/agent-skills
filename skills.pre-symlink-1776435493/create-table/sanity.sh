#!/usr/bin/env bash
# Sanity check for fixture-table skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Sanity check for fixture-table ==="

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

# Check run.sh exists and is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "WARN: run.sh not found or not executable"
else
    echo "PASS: run.sh exists and is executable"
fi

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

# Check reportlab is available (required for table generation)
if python3 -c "from reportlab.lib import colors" 2>/dev/null; then
    echo "PASS: reportlab available"
else
    echo "WARN: reportlab not installed (pip install reportlab)"
fi

echo "=== Sanity check complete ==="
