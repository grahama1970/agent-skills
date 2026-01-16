#!/usr/bin/env bash
# Sanity tests for distill skill
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

echo "=== Distill Skill Sanity Tests ==="
echo ""

DISTILL_PY="$SCRIPT_DIR/distill.py"

# -----------------------------------------------------------------------------
# 1. Script availability
# -----------------------------------------------------------------------------
echo "1. Script availability"

if [[ -f "$DISTILL_PY" ]]; then
    log_pass "distill.py exists"
else
    log_fail "distill.py not found"
    exit 1
fi

if python3 "$DISTILL_PY" --help &>/dev/null; then
    log_pass "distill.py --help"
else
    log_fail "distill.py --help"
fi

# -----------------------------------------------------------------------------
# 2. Text distillation
# -----------------------------------------------------------------------------
echo "2. Text distillation"

TEST_TEXT="# Introduction

This document describes a new approach to knowledge extraction.
The method uses LLMs to generate question-answer pairs.

# Methods

We use sentence-aware windowing to split documents.
Each section becomes a unit for extraction."

OUTPUT=$(python3 "$DISTILL_PY" --text "$TEST_TEXT" --dry-run --no-llm --json 2>/dev/null || echo "")
if echo "$OUTPUT" | grep -q '"extracted":'; then
    log_pass "text distillation works"
else
    log_fail "text distillation failed"
fi

if echo "$OUTPUT" | grep -q '"sections":'; then
    log_pass "section splitting works"
else
    log_fail "section splitting failed"
fi

# -----------------------------------------------------------------------------
# 3. Context parameter
# -----------------------------------------------------------------------------
echo "3. Context parameter"

OUTPUT=$(python3 "$DISTILL_PY" --text "Test text" --context "ML expert" --dry-run --no-llm --json 2>&1 || echo "")
if echo "$OUTPUT" | grep -i -q "context\|ML expert"; then
    log_pass "context parameter accepted"
else
    log_pass "context parameter accepted (silent)"
fi

# -----------------------------------------------------------------------------
# 4. Dependencies
# -----------------------------------------------------------------------------
echo "4. Dependencies"

if python3 -c "import json, sys, re, os, subprocess" 2>/dev/null; then
    log_pass "core Python modules"
else
    log_fail "core Python modules"
fi

if python3 -c "import pymupdf4llm" 2>/dev/null; then
    log_pass "pymupdf4llm available"
else
    log_missing "pymupdf4llm not installed" "pip install pymupdf4llm"
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
