#!/bin/bash
# Sanity check for debug-pdf skill
# Verifies dependencies, sibling skills, and basic functionality

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_SKILLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Debug PDF Skill Sanity Check ==="
echo ""

PASS=0
FAIL=0

check() {
    local name="$1"
    local result="$2"
    if [[ "$result" == OK* ]]; then
        echo "  [OK] $name"
        ((PASS++)) || true
    else
        echo "  [FAIL] $name: $result"
        ((FAIL++)) || true
    fi
}

# 1. Check Python dependencies
echo "1. Dependencies..."
if python3 -c "import fitz" 2>/dev/null; then
    check "PyMuPDF (fitz)" "OK"
else
    check "PyMuPDF (fitz)" "Not installed"
fi

if python3 -c "import httpx" 2>/dev/null; then
    check "httpx" "OK"
else
    check "httpx" "Not installed"
fi

if python3 -c "import typer" 2>/dev/null; then
    check "typer" "OK"
else
    check "typer" "Not installed"
fi

# 2. Check sibling skills exist
echo ""
echo "2. Sibling skills..."
if [[ -x "$PI_SKILLS_DIR/fetcher/run.sh" ]]; then
    check "fetcher skill" "OK"
else
    check "fetcher skill" "Not found at $PI_SKILLS_DIR/fetcher/run.sh"
fi

if [[ -x "$PI_SKILLS_DIR/fixture-tricky/run.sh" ]]; then
    check "fixture-tricky skill" "OK"
else
    check "fixture-tricky skill" "Not found at $PI_SKILLS_DIR/fixture-tricky/run.sh"
fi

if [[ -x "$PI_SKILLS_DIR/extractor/run.sh" ]]; then
    check "extractor skill" "OK"
else
    check "extractor skill" "Not found (optional)"
fi

# 3. Check agent-inbox availability
echo ""
echo "3. Agent inbox..."
MEMORY_SKILLS="${MEMORY_SKILLS_DIR:-/home/graham/workspace/experiments/memory/.agents/skills}"
if [[ -x "$MEMORY_SKILLS/agent-inbox/agent-inbox" ]]; then
    check "agent-inbox tool" "OK"
elif [[ -x "$MEMORY_SKILLS/agent-inbox/run.sh" ]]; then
    check "agent-inbox tool (via run.sh)" "OK"
else
    check "agent-inbox tool" "Not found (inbox notifications disabled)"
fi

# 4. Check data directory
echo ""
echo "4. Data directory..."
DATA_DIR="${DEBUG_PDF_DATA:-$HOME/.pi/debug-pdf}"
mkdir -p "$DATA_DIR" 2>/dev/null || true
if [[ -d "$DATA_DIR" ]]; then
    check "Data directory" "OK ($DATA_DIR)"
else
    check "Data directory" "Could not create $DATA_DIR"
fi

# 5. Test help output
echo ""
echo "5. CLI interface..."
if "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1; then
    check "run.sh --help" "OK"
else
    check "run.sh --help" "Failed"
fi

# 6. Test list-patterns
echo ""
echo "6. Pattern listing..."
PATTERNS=$("$SCRIPT_DIR/run.sh" list-patterns 2>&1)
if echo "$PATTERNS" | grep -q "scanned_no_ocr"; then
    check "list-patterns output" "OK"
else
    check "list-patterns output" "Missing expected patterns"
fi

# 7. Quick import test
echo ""
echo "7. Python module..."
cd "$SCRIPT_DIR"
if [[ -d .venv ]]; then
    source .venv/bin/activate 2>/dev/null || true
fi

IMPORT_TEST=$(python3 -c "
import sys
sys.path.insert(0, '.')
try:
    import debug_pdf
    print('OK')
except ImportError as e:
    print(f'FAIL: {e}')
except Exception as e:
    print(f'FAIL: {e}')
" 2>&1)

if [[ "$IMPORT_TEST" == "OK" ]]; then
    check "debug_pdf module import" "OK"
else
    check "debug_pdf module import" "$IMPORT_TEST"
fi

# Summary
echo ""
echo "============================================================"
TOTAL=$((PASS + FAIL))
if [[ $FAIL -eq 0 ]]; then
    echo "SANITY CHECK COMPLETE: ${PASS}/${TOTAL} checks passed"
    echo "============================================================"
    exit 0
else
    echo "SANITY CHECK: ${PASS}/${TOTAL} passed, ${FAIL} failed"
    echo "============================================================"
    echo ""
    echo "To fix missing dependencies:"
    echo "  cd $SCRIPT_DIR && uv pip install -e ."
    exit 1
fi
