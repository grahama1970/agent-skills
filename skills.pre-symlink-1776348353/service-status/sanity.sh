#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "service-status sanity check..."

# Check run.sh exists and is executable
if [ ! -x "$SCRIPT_DIR/run.sh" ]; then
  echo "FAIL: run.sh not found or not executable"
  exit 1
fi

# Check curl is available
if ! command -v curl >/dev/null 2>&1; then
  echo "FAIL: curl command not found"
  exit 1
fi

# Check python3 is available
if ! command -v python3 >/dev/null 2>&1; then
  echo "FAIL: python3 command not found"
  exit 1
fi

# Test that run.sh can execute and produces daemon status table
output=$("$SCRIPT_DIR/run.sh" 2>&1 || true)
if echo "$output" | grep -q "DAEMON"; then
  echo "PASS: service-status sanity check"
  exit 0
else
  echo "FAIL: run.sh did not produce expected output"
  exit 1
fi
