#!/bin/bash
# Run all sanity scripts for interview skill v2
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Interview Skill v2 Sanity Checks ==="
echo

cd "$SKILL_DIR"

# Use uv to run in the skill's environment
if command -v uv &> /dev/null; then
    PYTHON="uv run python"
else
    PYTHON="python3"
fi

FAILED=0

echo "[1/2] Testing Textual TabbedContent API..."
if $PYTHON "$SCRIPT_DIR/textual_tabs.py"; then
    echo "  ✓ Textual TabbedContent OK"
else
    echo "  ✗ Textual TabbedContent FAILED"
    FAILED=1
fi
echo

echo "[2/2] Testing Pillow image handling..."
if $PYTHON "$SCRIPT_DIR/pillow.py"; then
    echo "  ✓ Pillow OK"
else
    echo "  ✗ Pillow FAILED"
    FAILED=1
fi
echo

if [ $FAILED -eq 0 ]; then
    echo "=== ALL SANITY CHECKS PASSED ==="
    exit 0
else
    echo "=== SOME SANITY CHECKS FAILED ==="
    exit 1
fi
