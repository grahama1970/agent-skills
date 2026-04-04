#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "paper-lab sanity check..."

# Check SKILL.md exists
if [ ! -f "$SCRIPT_DIR/SKILL.md" ]; then
  echo "FAIL: SKILL.md not found"
  exit 1
fi

# Check run.sh exists and is executable
if [ ! -x "$SCRIPT_DIR/run.sh" ]; then
  echo "FAIL: run.sh not found or not executable"
  exit 1
fi

# Test that run.sh can be invoked (spec-only skill, should exit 1 with message)
output=$("$SCRIPT_DIR/run.sh" 2>&1 || true)
if echo "$output" | grep -q "SPECIFICATION ONLY"; then
  echo "PASS: paper-lab sanity check (spec-only skill)"
  exit 0
else
  echo "FAIL: run.sh did not show expected spec message"
  exit 1
fi
