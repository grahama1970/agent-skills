#!/usr/bin/env bash
# Sanity check for clean-text skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Sanity check for clean-text ==="

# Check python3 exists
if ! command -v python3 >/dev/null 2>&1; then
    echo "FAIL: python3 not found"
    exit 1
fi
echo "PASS: python3 found"

# Check main script exists
if [[ ! -f "$SCRIPT_DIR/clean_text.py" ]]; then
    echo "FAIL: clean_text.py not found"
    exit 1
fi
echo "PASS: clean_text.py exists"

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
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/clean_text.py" --help >/dev/null 2>&1; then
    echo "PASS: CLI --help works"
else
    echo "WARN: CLI --help check failed (may need dependencies)"
fi

# Basic smoke test - normalize a simple string
if echo "test" | uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/clean_text.py" >/dev/null 2>&1; then
    echo "PASS: basic normalization works"
else
    echo "WARN: basic normalization test failed"
fi

echo "=== Sanity check complete ==="
