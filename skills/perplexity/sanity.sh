#!/usr/bin/env bash
# Sanity tests for perplexity skill

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }

echo "=== perplexity Skill Sanity Tests ==="
echo ""

# 1. Script exists
echo "1. Script availability"
if [[ -f "$SCRIPT_DIR/perplexity.py" ]]; then
    log_pass "perplexity.py exists"
else
    log_fail "perplexity.py not found"
    exit 1
fi

# 2. Shows help
echo "2. CLI help"
OUTPUT=$(python "$SCRIPT_DIR/perplexity.py" --help 2>&1 || true)
if echo "$OUTPUT" | grep -q "Research with web search"; then
    log_pass "shows help text"
else
    log_fail "no help text"
fi

# 3. Has ask subcommand
echo "3. ask subcommand"
OUTPUT=$(python "$SCRIPT_DIR/perplexity.py" ask --help 2>&1 || true)
if echo "$OUTPUT" | grep -q "Ask a question"; then
    log_pass "ask subcommand works"
else
    log_fail "ask subcommand missing"
fi

# 4. Has research subcommand
echo "4. research subcommand"
OUTPUT=$(python "$SCRIPT_DIR/perplexity.py" research --help 2>&1 || true)
if echo "$OUTPUT" | grep -q "Research a question"; then
    log_pass "research subcommand works"
else
    log_fail "research subcommand missing"
fi

# 5. Has models subcommand
echo "5. models subcommand"
OUTPUT=$(python "$SCRIPT_DIR/perplexity.py" models 2>&1 || true)
if echo "$OUTPUT" | grep -q "sonar"; then
    log_pass "models subcommand works"
else
    log_fail "models subcommand missing"
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
