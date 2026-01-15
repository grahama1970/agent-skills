#!/usr/bin/env bash
# Sanity tests for arxiv skill

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }

echo "=== arxiv Skill Sanity Tests ==="
echo ""

# 1. Script exists
echo "1. Script availability"
if [[ -f "$SCRIPT_DIR/arxiv_cli.py" ]]; then
    log_pass "arxiv_cli.py exists"
else
    log_fail "arxiv_cli.py not found"
    exit 1
fi

# 2. Shows help
echo "2. CLI help"
OUTPUT=$(python "$SCRIPT_DIR/arxiv_cli.py" --help 2>&1 || true)
if echo "$OUTPUT" | grep -qi "arxiv\|search\|paper"; then
    log_pass "shows help text"
else
    log_fail "no help text"
fi

# 3. Has search subcommand
echo "3. search subcommand"
OUTPUT=$(python "$SCRIPT_DIR/arxiv_cli.py" search --help 2>&1 || true)
if echo "$OUTPUT" | grep -qi "query\|search"; then
    log_pass "search subcommand works"
else
    log_fail "search subcommand missing"
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
