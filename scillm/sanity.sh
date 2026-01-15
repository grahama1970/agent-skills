#!/usr/bin/env bash
# Sanity tests for scillm skill

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }

echo "=== scillm Skill Sanity Tests ==="
echo ""

# 1. Scripts exist
echo "1. Script availability"
if [[ -f "$SCRIPT_DIR/batch.py" ]]; then
    log_pass "batch.py exists"
else
    log_fail "batch.py not found"
fi

if [[ -f "$SCRIPT_DIR/prove.py" ]]; then
    log_pass "prove.py exists"
else
    log_fail "prove.py not found"
fi

# 2. batch.py shows help
echo "2. batch.py help"
OUTPUT=$(python "$SCRIPT_DIR/batch.py" --help 2>&1 || true)
if echo "$OUTPUT" | grep -qi "batch\|llm\|completion"; then
    log_pass "batch.py shows help"
else
    log_fail "batch.py no help"
fi

# 3. prove.py shows help
echo "3. prove.py help"
OUTPUT=$(python "$SCRIPT_DIR/prove.py" --help 2>&1 || true)
if echo "$OUTPUT" | grep -qi "prove\|lean"; then
    log_pass "prove.py shows help"
else
    log_fail "prove.py no help"
fi

# Summary
echo ""
echo "=== Summary ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo ""
if [[ $FAIL -gt 0 ]]; then
    echo "Result: FAIL"
    exit 1
else
    echo "Result: PASS"
    exit 0
fi
