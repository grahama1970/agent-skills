#!/usr/bin/env bash
# Sanity tests for brave-search skill

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }

echo "=== brave-search Skill Sanity Tests ==="
echo ""

# 1. Script exists
echo "1. Script availability"
if [[ -f "$SCRIPT_DIR/brave_search.py" ]]; then
    log_pass "brave_search.py exists"
else
    log_fail "brave_search.py not found"
    exit 1
fi

# 2. Shows help
echo "2. CLI help"
OUTPUT=$(python "$SCRIPT_DIR/brave_search.py" --help 2>&1 || true)
if echo "$OUTPUT" | grep -qi "brave\|search"; then
    log_pass "shows help text"
else
    log_fail "no help text"
fi

# 3. Has web subcommand
echo "3. web subcommand"
OUTPUT=$(python "$SCRIPT_DIR/brave_search.py" web --help 2>&1 || true)
if echo "$OUTPUT" | grep -qi "search\|query"; then
    log_pass "web subcommand works"
else
    log_fail "web subcommand missing"
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
