#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Orchestrate Skill Sanity Tests ==="

echo "1. Script availability"
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh is executable"
else
    echo "  [FAIL] run.sh missing or not executable"
    exit 1
fi

echo "2. Help command"
if "$SCRIPT_DIR/run.sh" --help > /dev/null; then
    echo "  [PASS] run.sh --help works"
else
    echo "  [FAIL] run.sh --help failed"
    exit 1
fi

# Detect backend for information
BACKEND=$("$SCRIPT_DIR/run.sh" run 2>&1 | grep "backend" || echo "unknown")
# Note: actual run test requires a task file, which we skip in basic sanity check to avoid side effects.

echo ""
echo "Result: PASS"
exit 0
