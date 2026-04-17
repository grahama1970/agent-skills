#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "export-oscal sanity check..."

# Check run.sh exists and is executable
if [ ! -x "$SCRIPT_DIR/run.sh" ]; then
  echo "FAIL: run.sh not found or not executable"
  exit 1
fi

# Run dry-run export and capture output
output=$("$SCRIPT_DIR/run.sh" export --framework NIST-800-171 --dry-run 2>&1)
if [ $? -ne 0 ]; then
  echo "FAIL: dry-run export exited non-zero"
  echo "$output"
  exit 1
fi

# Write to temp file for validation
tmpfile=$(mktemp /tmp/oscal-sanity-XXXXXX.json)
trap 'rm -f "$tmpfile"' EXIT
echo "$output" > "$tmpfile"

# Validate the output using the validate subcommand
validate_output=$("$SCRIPT_DIR/run.sh" validate "$tmpfile" 2>&1)
if [ $? -ne 0 ]; then
  echo "FAIL: validation of dry-run output failed"
  echo "$validate_output"
  exit 1
fi

echo "PASS: export-oscal sanity check"
echo "  $validate_output"
exit 0
