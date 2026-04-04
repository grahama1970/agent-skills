#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[sanity] Testing streamdeck-lab..."

# Check entry point exists
[ -x "$SKILL_DIR/run.sh" ] || { echo "FAIL: run.sh not found or not executable"; exit 1; }

# Check main module exists
[ -f "$SKILL_DIR/streamdeck_lab.py" ] || { echo "FAIL: streamdeck_lab.py not found"; exit 1; }

# Check Python syntax
python3 -c "import sys; sys.path.insert(0, '$SKILL_DIR'); import ast; ast.parse(open('$SKILL_DIR/streamdeck_lab.py').read())" 2>/dev/null || { echo "FAIL: streamdeck_lab.py has syntax errors"; exit 1; }

echo "[sanity] streamdeck-lab: PASS"
