#!/usr/bin/env bash
# Sanity tests for context7 skill

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }

echo "=== context7 Skill Sanity Tests ==="
echo ""

# 1. Script exists
echo "1. Script availability"
if [[ -f "$SCRIPT_DIR/context7.py" ]]; then
    log_pass "context7.py exists"
else
    log_fail "context7.py not found"
    exit 1
fi

# 2. Shows help
echo "2. CLI help"
OUTPUT=$(python "$SCRIPT_DIR/context7.py" --help 2>&1 || true)
if echo "$OUTPUT" | grep -q "Context7"; then
    log_pass "shows help text"
else
    log_fail "no help text"
fi

# 3. Has search subcommand
echo "3. search subcommand"
OUTPUT=$(python "$SCRIPT_DIR/context7.py" search --help 2>&1 || true)
if echo "$OUTPUT" | grep -q "library"; then
    log_pass "search subcommand works"
else
    log_fail "search subcommand missing"
fi

# 4. Has context subcommand
echo "4. context subcommand"
OUTPUT=$(python "$SCRIPT_DIR/context7.py" context --help 2>&1 || true)
if echo "$OUTPUT" | grep -q "query"; then
    log_pass "context subcommand works"
else
    log_fail "context subcommand missing"
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
