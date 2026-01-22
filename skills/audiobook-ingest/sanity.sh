#!/usr/bin/env bash
# Sanity tests for audiobook-ingest skill

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }

echo "=== audiobook-ingest Skill Sanity Tests ==="
echo ""

# 1. Script exists and is executable
echo "1. Script availability"
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    log_pass "run.sh exists and is executable"
else
    log_fail "run.sh missing or not executable"
    exit 1
fi

# 2. Shows help
echo "2. CLI help"
OUTPUT=$("$SCRIPT_DIR/run.sh" help 2>&1 || true)
if echo "$OUTPUT" | grep -qi "usage\|command"; then
    log_pass "shows help text"
else
    log_fail "no help text"
fi

# 3. Required binaries check (uv)
echo "3. Required binaries"
if command -v uv &>/dev/null; then
    log_pass "uv is installed"
else
    log_fail "uv not found (install from https://docs.astral.sh/uv/)"
fi

# 4. Directory structure
echo "4. Directory setup"
INBOX="${HOME}/clawd/library/inbox"
LIBRARY="${HOME}/clawd/library/books"

# Run a simple command to ensure directories are created
"$SCRIPT_DIR/run.sh" help >/dev/null 2>&1 || true

if [[ -d "$INBOX" ]] && [[ -d "$LIBRARY" ]]; then
    log_pass "library directories exist"
else
    log_fail "library directories not created"
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
