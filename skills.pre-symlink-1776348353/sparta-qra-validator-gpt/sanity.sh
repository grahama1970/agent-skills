#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "sparta-qra-validator-gpt sanity check..."

# Check pyproject.toml exists
if [ ! -f "$SCRIPT_DIR/pyproject.toml" ]; then
  echo "FAIL: pyproject.toml not found"
  exit 1
fi

# Check scripts/validate.py exists
if [ ! -f "$SCRIPT_DIR/scripts/validate.py" ]; then
  echo "FAIL: scripts/validate.py not found"
  exit 1
fi

# Test help command via run.sh
output=$("$SCRIPT_DIR/run.sh" help 2>&1 || true)
if ! echo "$output" | grep -q "heuristic"; then
  echo "FAIL: run.sh help did not show expected output"
  exit 1
fi

# Test that validate.py exists and is readable
if [ ! -r "$SCRIPT_DIR/scripts/validate.py" ]; then
  echo "FAIL: scripts/validate.py not readable"
  exit 1
fi

echo "PASS: sparta-qra-validator-gpt sanity check"
exit 0
