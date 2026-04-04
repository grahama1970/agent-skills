#!/usr/bin/env bash
#
# Run all sanity scripts for create-story skill
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Running all sanity scripts ==="
echo ""

PASS=0
FAIL=0

for script in "$SCRIPT_DIR"/*.sh; do
    [[ "$(basename "$script")" == "run_all.sh" ]] && continue

    name=$(basename "$script" .sh)
    echo "--- $name ---"

    if bash "$script"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
    fi
    echo ""
done

echo "=== Results ==="
echo "PASS: $PASS"
echo "FAIL: $FAIL"

if [[ $FAIL -gt 0 ]]; then
    echo ""
    echo "Some sanity checks failed. Fix issues before proceeding."
    exit 1
fi

echo ""
echo "All sanity checks passed!"
exit 0
