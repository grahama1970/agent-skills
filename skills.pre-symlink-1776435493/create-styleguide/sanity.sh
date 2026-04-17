#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== create-styleguide sanity check ==="

# Syntax check all Python files
for f in "${SCRIPT_DIR}"/*.py; do
    python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" || {
        echo "FAIL: syntax error in $(basename "$f")"
        exit 1
    }
done
echo "Syntax: all .py files OK"

# Run dry-run
OUTPUT=$("${SCRIPT_DIR}/run.sh" dry-run 2>&1)

PASS=true
for token in "PASS" "dry-run" "verified"; do
    if ! echo "$OUTPUT" | grep -qi "$token"; then
        echo "FAIL: missing expected token '$token' in dry-run output"
        PASS=false
    fi
done

if [ "$PASS" = true ]; then
    echo "PASS: dry-run annotation + debt + diff + assembly verified"
    exit 0
else
    echo ""
    echo "--- output ---"
    echo "$OUTPUT"
    exit 1
fi
