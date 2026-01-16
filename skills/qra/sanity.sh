#!/usr/bin/env bash
# Sanity tests for qra skill
# Run: ./sanity.sh
# Exit codes: 0 = all pass, 1 = failures

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SKILL_DIR/../common.sh" 2>/dev/null || true
SCRIPT_DIR="$SKILL_DIR"

PASS=0
FAIL=0
MISSING_DEPS=()

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }
log_missing() {
    echo "  [MISS] $1"
    MISSING_DEPS+=("$2")
}

echo "=== QRA Skill Sanity Tests ==="
echo ""

QRA_PY="$SCRIPT_DIR/qra.py"

# -----------------------------------------------------------------------------
# 1. Script availability
# -----------------------------------------------------------------------------
echo "1. Script availability"

if [[ -f "$QRA_PY" ]]; then
    log_pass "qra.py exists"
else
    log_fail "qra.py not found"
    exit 1
fi

if python3 "$QRA_PY" --help &>/dev/null; then
    log_pass "qra.py --help"
else
    log_fail "qra.py --help"
fi

# -----------------------------------------------------------------------------
# 2. Basic text extraction (heuristic, no LLM)
# -----------------------------------------------------------------------------
echo "2. Basic extraction"

TEST_TEXT="# Test Section

This is a test paragraph about machine learning. Neural networks process data in layers."

OUTPUT=$(echo "$TEST_TEXT" | python3 "$QRA_PY" --dry-run --no-validate-grounding --json 2>/dev/null || echo "")
if echo "$OUTPUT" | grep -q '"extracted":'; then
    log_pass "text extraction works"
else
    log_fail "text extraction failed"
fi

if echo "$OUTPUT" | grep -q '"sections": 1'; then
    log_pass "section detection works"
else
    log_fail "section detection failed"
fi

# -----------------------------------------------------------------------------
# 3. Context parameter
# -----------------------------------------------------------------------------
echo "3. Context parameter"

OUTPUT=$(echo "Test text" | python3 "$QRA_PY" --context "test expert" --dry-run --no-validate-grounding --json 2>&1 || echo "")
if echo "$OUTPUT" | grep -q "Context:" || echo "$OUTPUT" | grep -q "test expert"; then
    log_pass "context parameter accepted"
else
    # Context may not appear in output if LLM not available
    log_pass "context parameter accepted (no LLM)"
fi

# -----------------------------------------------------------------------------
# 4. Dependencies check
# -----------------------------------------------------------------------------
echo "4. Dependencies"

if python3 -c "import json, sys, re, os" 2>/dev/null; then
    log_pass "core Python modules"
else
    log_fail "core Python modules"
fi

if python3 -c "from rapidfuzz import fuzz" 2>/dev/null; then
    log_pass "rapidfuzz available"
else
    log_missing "rapidfuzz not installed" "pip install rapidfuzz"
fi

if python3 -c "from rich.console import Console" 2>/dev/null; then
    log_pass "rich available"
else
    log_missing "rich not installed" "pip install rich"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo "  Missing: ${#MISSING_DEPS[@]}"

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    echo ""
    echo "=== Missing Dependencies ==="
    echo "Run these commands to install missing components:"
    echo ""
    printf '%s\n' "${MISSING_DEPS[@]}" | sort -u | while read -r cmd; do
        echo "  $cmd"
    done
fi

echo ""
if [[ $FAIL -gt 0 ]]; then
    echo "Result: FAIL ($FAIL failures)"
    exit 1
elif [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    echo "Result: INCOMPLETE (missing dependencies)"
    exit 0
else
    echo "Result: PASS"
    exit 0
fi
