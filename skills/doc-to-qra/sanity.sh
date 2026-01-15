#!/usr/bin/env bash
# Sanity tests for doc-to-qra skill

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0
FAIL=0

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }

echo "=== doc-to-qra Skill Sanity Tests ==="
echo ""

# 1. Script exists
echo "1. Script availability"
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    log_pass "run.sh exists and executable"
else
    log_fail "run.sh not found"
    exit 1
fi

# 2. Usage message
echo "2. Usage message"
OUTPUT=$("$SCRIPT_DIR/run.sh" 2>&1 || true)
if echo "$OUTPUT" | grep -q "Usage:"; then
    log_pass "shows usage when no args"
else
    log_fail "no usage message"
fi

# 3. File ingestion (dry-run)
echo "3. File ingestion"
echo "Test content about machine learning." > /tmp/ingest_test.txt
OUTPUT=$("$SCRIPT_DIR/run.sh" /tmp/ingest_test.txt test --dry-run 2>&1 || true)
if echo "$OUTPUT" | grep -qi "distill\|extract\|section"; then
    log_pass "file ingestion works"
else
    log_fail "file ingestion failed"
fi
rm -f /tmp/ingest_test.txt

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
