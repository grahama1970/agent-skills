#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Interview Skill Sanity ==="
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh exists"
else
    echo "  [FAIL] run.sh missing"
    exit 1
fi
# Verify run.sh actually executes (--help should exit 0)
if "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1; then
    echo "  [PASS] run.sh execution"
else
    echo "  [FAIL] run.sh execution failed"
    exit 1
fi
echo "Result: PASS"
