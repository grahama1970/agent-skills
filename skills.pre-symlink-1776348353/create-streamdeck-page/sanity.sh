#!/usr/bin/env bash
# Sanity check for create-streamdeck-page skill
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== create-streamdeck-page sanity check ==="

# Check required files exist
for f in SKILL.md run.sh create_page.py pyproject.toml; do
    if [ ! -f "$SKILL_DIR/$f" ]; then
        echo "FAIL: Missing $f"
        exit 1
    fi
done
echo "PASS: All required files present"

# Syntax check
python3 -c "import ast; ast.parse(open('$SKILL_DIR/create_page.py').read())"
echo "PASS: Python syntax OK"

# Check ground truth is valid JSON
python3 -c "import json; json.load(open('$SKILL_DIR/ground_truth/contexts.json'))"
echo "PASS: Ground truth JSON valid"

# Check streamdeck CLI exists
CLI="$HOME/workspace/streamdeck/.venv/bin/streamdeck-cli"
if [ -x "$CLI" ]; then
    echo "PASS: streamdeck CLI found"
else
    echo "WARN: streamdeck CLI not found at $CLI (may need venv setup)"
fi

echo "=== All checks passed ==="
