#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== create-design-board sanity check ==="

# dry-run creates synthetic images, generates composite + markdown, validates both
OUTPUT=$("${SCRIPT_DIR}/run.sh" dry-run 2>&1)

PASS=true

for token in "PASS" "dry-run" "verified"; do
    if ! echo "$OUTPUT" | grep -qi "$token"; then
        echo "FAIL: missing expected token '$token' in dry-run output"
        PASS=false
    fi
done

if [ "$PASS" = true ]; then
    echo "PASS: dry-run composite + markdown generation verified"
    exit 0
else
    echo ""
    echo "--- output ---"
    echo "$OUTPUT"
    exit 1
fi
