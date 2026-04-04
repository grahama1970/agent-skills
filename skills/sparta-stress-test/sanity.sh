#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORY_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "sparta-stress-test sanity check..."

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

# Test help via CLI (should show usage without errors)
output=$("$SCRIPT_DIR/run.sh" --help 2>&1 || true)
if ! echo "$output" | grep -q "Stress test"; then
  echo "FAIL: run.sh --help did not show expected output"
  exit 1
fi

# Check sparta_stress_test module directory exists
if [ ! -d "$SCRIPT_DIR/sparta_stress_test" ]; then
  echo "FAIL: sparta_stress_test module directory not found"
  exit 1
fi

echo "PASS: sparta-stress-test sanity check"
exit 0
