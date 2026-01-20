#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Episodic Archiver Sanity ==="
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh exists"
else
    echo "  [FAIL] run.sh missing"
    exit 1
fi
# Basic help check (script expects args, so usage message is success, even if exit code is 1)
OUTPUT=$("$SCRIPT_DIR/run.sh" 2>&1 || true)
if echo "$OUTPUT" | grep -i "Usage" >/dev/null; then
    echo "  [PASS] run.sh help/usage works"
else
    echo "  [FAIL] run.sh failed to show usage"
    echo "Output: $OUTPUT"
    exit 1
fi
echo "Result: PASS"
