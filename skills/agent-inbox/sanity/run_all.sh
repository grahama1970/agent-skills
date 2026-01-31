#!/usr/bin/env bash
# Run all sanity scripts for agent-inbox headless dispatch
# Exit 0 only if ALL scripts pass

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  Agent-Inbox Sanity Checks"
echo "=========================================="
echo ""

PASS_COUNT=0
FAIL_COUNT=0
RESULTS=()

run_check() {
    local name="$1"
    local script="$2"

    echo "----------------------------------------"
    echo "Running: $name"
    echo "----------------------------------------"

    if python3 "$script"; then
        PASS_COUNT=$((PASS_COUNT + 1))
        RESULTS+=("PASS: $name")
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        RESULTS+=("FAIL: $name")
    fi
    echo ""
}

# Run each sanity script
run_check "subprocess detachment" "subprocess_detach.py"
run_check "task-monitor API" "task_monitor_api.py"
run_check "CLI headless mode" "pi_headless.py"

# Summary
echo "=========================================="
echo "  SUMMARY"
echo "=========================================="
for result in "${RESULTS[@]}"; do
    echo "  $result"
done
echo ""
echo "  Total: $PASS_COUNT passed, $FAIL_COUNT failed"
echo "=========================================="

if [ $FAIL_COUNT -gt 0 ]; then
    echo "FAIL: Not all sanity checks passed"
    exit 1
else
    echo "PASS: All sanity checks passed"
    exit 0
fi
