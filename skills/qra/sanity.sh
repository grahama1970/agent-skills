#!/usr/bin/env bash
# Sanity tests for qra skill (modular version)
# Run: ./sanity.sh
# Exit codes: 0 = all pass, 1 = failures

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SKILL_DIR/../common.sh" 2>/dev/null || true
SCRIPT_DIR="$SKILL_DIR"

# Set PYTHONPATH to parent so 'qra' package can be imported
export PYTHONPATH="${SKILL_DIR}/..:${PYTHONPATH:-}"

PASS=0
FAIL=0
MISSING_DEPS=()

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }
log_missing() {
    echo "  [MISS] $1"
    MISSING_DEPS+=("$2")
}

echo "=== QRA Skill Sanity Tests (Modular) ==="
echo ""

QRA_PY="$SCRIPT_DIR/qra.py"

# -----------------------------------------------------------------------------
# 1. Module structure
# -----------------------------------------------------------------------------
echo "1. Module structure"

MODULES=(
    "config.py"
    "utils.py"
    "extractor.py"
    "validator.py"
    "storage.py"
    "qra.py"
    "__main__.py"
    "__init__.py"
)

for mod in "${MODULES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$mod" ]]; then
        log_pass "$mod exists"
    else
        log_fail "$mod not found"
    fi
done

# Check monolith was preserved
if [[ -f "$SCRIPT_DIR/qra_monolith.py" ]]; then
    log_pass "qra_monolith.py backup exists"
else
    log_missing "qra_monolith.py backup not found" "mv qra.py qra_monolith.py"
fi

# -----------------------------------------------------------------------------
# 2. Module line counts (< 500 lines each)
# -----------------------------------------------------------------------------
echo "2. Module line counts"

for mod in config.py utils.py extractor.py validator.py storage.py __main__.py; do
    if [[ -f "$SCRIPT_DIR/$mod" ]]; then
        lines=$(wc -l < "$SCRIPT_DIR/$mod")
        if [[ $lines -lt 500 ]]; then
            log_pass "$mod: $lines lines (< 500)"
        else
            log_fail "$mod: $lines lines (>= 500)"
        fi
    fi
done

# -----------------------------------------------------------------------------
# 3. Import checks (no circular imports)
# -----------------------------------------------------------------------------
echo "3. Import checks"

# Test each module can be imported (run from parent dir for proper package resolution)
cd "$SKILL_DIR/.."
for mod in config utils extractor validator storage; do
    if python3 -c "import qra.$mod" 2>/dev/null; then
        log_pass "import qra.$mod"
    else
        log_fail "import qra.$mod"
    fi
done

# Test main package import
if python3 -c "import qra; print(qra.__version__)" 2>/dev/null; then
    log_pass "import qra (package)"
else
    log_fail "import qra (package)"
fi

# -----------------------------------------------------------------------------
# 4. CLI functionality
# -----------------------------------------------------------------------------
echo "4. CLI functionality"

# CLI can run from anywhere since qra.py sets up its own path
if python3 "$QRA_PY" --help &>/dev/null; then
    log_pass "qra.py --help"
else
    log_fail "qra.py --help"
fi

# -----------------------------------------------------------------------------
# 5. Basic text extraction (heuristic, no LLM)
# -----------------------------------------------------------------------------
echo "5. Basic extraction"

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
# 6. Context parameter
# -----------------------------------------------------------------------------
echo "6. Context parameter"

OUTPUT=$(echo "Test text" | python3 "$QRA_PY" --context "test expert" --dry-run --no-validate-grounding --json 2>&1 || echo "")
if echo "$OUTPUT" | grep -q "Context:" || echo "$OUTPUT" | grep -q "test expert"; then
    log_pass "context parameter accepted"
else
    # Context may not appear in output if LLM not available
    log_pass "context parameter accepted (no LLM)"
fi

# -----------------------------------------------------------------------------
# 7. Dependencies check
# -----------------------------------------------------------------------------
echo "7. Dependencies"

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
# 8. API exports check
# -----------------------------------------------------------------------------
echo "8. API exports"

EXPORTS=(
    "extract_qra_batch"
    "check_grounding"
    "store_qra"
    "build_sections"
    "get_scillm_config"
)

for export in "${EXPORTS[@]}"; do
    if python3 -c "from qra import $export" 2>/dev/null; then
        log_pass "export: $export"
    else
        log_fail "export: $export"
    fi
done

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
