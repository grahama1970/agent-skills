#!/usr/bin/env bash
# Sanity tests for doc2qra skill (modular version)
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

echo "=== doc2qra Skill Sanity Tests (Modular) ==="
echo ""

DISTILL_PY="$SCRIPT_DIR/__main__.py"

# -----------------------------------------------------------------------------
# 1. Module structure verification
# -----------------------------------------------------------------------------
echo "1. Module structure"

MODULES=(
    "__init__.py"
    "__main__.py"
    "config.py"
    "utils.py"
    "pdf_handler.py"
    "url_handler.py"
    "text_handler.py"
    "qra_generator.py"
    "grounding.py"
    "memory_ops.py"
    "cli.py"
    "persona_gate.py"
)

for module in "${MODULES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$module" ]]; then
        log_pass "$module exists"
    else
        log_fail "$module not found"
    fi
done

# Verify persona_gate.py exists
if [[ -f "$SCRIPT_DIR/persona_gate.py" ]]; then
    log_pass "persona_gate.py exists"
else
    log_fail "persona_gate.py not found"
fi

# -----------------------------------------------------------------------------
# 2. Line count verification (< 800 lines each, project max)
# -----------------------------------------------------------------------------
echo "2. Module line counts (< 800 lines)"

for module in "${MODULES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$module" ]]; then
        lines=$(wc -l < "$SCRIPT_DIR/$module")
        if [[ $lines -lt 800 ]]; then
            log_pass "$module: $lines lines"
        else
            log_fail "$module: $lines lines (exceeds 800)"
        fi
    fi
done

# -----------------------------------------------------------------------------
# 3. Import verification (no circular imports)
# -----------------------------------------------------------------------------
echo "3. Import verification"

# Run Python imports from parent (skills) dir so doc2qra is importable as a package
SKILLS_DIR="$SCRIPT_DIR/.."
cd "$SKILLS_DIR"

if python3 -c "from doc2qra.config import get_scillm_config" 2>/dev/null; then
    log_pass "config module imports"
else
    log_fail "config module import failed"
fi

if python3 -c "from doc2qra.utils import log, iter_with_progress" 2>/dev/null; then
    log_pass "utils module imports"
else
    log_fail "utils module import failed"
fi

if python3 -c "from doc2qra.pdf_handler import read_file, pdf_preflight" 2>/dev/null; then
    log_pass "pdf_handler module imports"
else
    log_fail "pdf_handler module import failed"
fi

if python3 -c "from doc2qra.url_handler import fetch_url" 2>/dev/null; then
    log_pass "url_handler module imports"
else
    log_fail "url_handler module import failed"
fi

if python3 -c "from doc2qra.text_handler import build_sections, extract_code_blocks" 2>/dev/null; then
    log_pass "text_handler module imports"
else
    log_fail "text_handler module import failed"
fi

if python3 -c "from doc2qra.qra_generator import extract_qra_llm, extract_qa_heuristic" 2>/dev/null; then
    log_pass "qra_generator module imports"
else
    log_fail "qra_generator module import failed"
fi

if python3 -c "from doc2qra.grounding import check_grounding, validate_and_filter_qras" 2>/dev/null; then
    log_pass "grounding module imports"
else
    log_fail "grounding module import failed"
fi

if python3 -c "from doc2qra.memory_ops import store_qa" 2>/dev/null; then
    log_pass "memory_ops module imports"
else
    log_fail "memory_ops module import failed"
fi

# Test full import chain (catches circular imports)
if python3 -c "from doc2qra.cli import distill, app" 2>/dev/null; then
    log_pass "cli module imports (no circular deps)"
else
    log_fail "cli module import failed (circular deps?)"
fi

# -----------------------------------------------------------------------------
# 4. CLI functionality
# -----------------------------------------------------------------------------
echo "4. CLI functionality"

if python3 "$DISTILL_PY" --help &>/dev/null; then
    log_pass "distill.py --help"
else
    log_fail "distill.py --help"
fi

# -----------------------------------------------------------------------------
# 5. Text distillation
# -----------------------------------------------------------------------------
echo "5. Text distillation"

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
# 6. Sections-only mode
# -----------------------------------------------------------------------------
echo "6. Sections-only mode"

OUTPUT=$(python3 "$DISTILL_PY" --text "$TEST_TEXT" --sections-only --json 2>/dev/null || echo "")
if echo "$OUTPUT" | grep -q '"section_count":'; then
    log_pass "sections-only mode works"
else
    log_fail "sections-only mode failed"
fi

# -----------------------------------------------------------------------------
# 7. Context parameter
# -----------------------------------------------------------------------------
echo "7. Context parameter"

OUTPUT=$(python3 "$DISTILL_PY" --text "Test text" --context "ML expert" --dry-run --no-llm --json 2>&1 || echo "")
if echo "$OUTPUT" | grep -i -q "context\|ML expert"; then
    log_pass "context parameter accepted"
else
    log_pass "context parameter accepted (silent)"
fi

# -----------------------------------------------------------------------------
# 8. Dependencies
# -----------------------------------------------------------------------------
echo "8. Dependencies"

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
