#!/bin/bash
# Sanity check for extractor skill (modular version)
# Verifies that all supported formats extract correctly
# Note: We don't use 'set -e' because ((PASS++)) returns false when PASS=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRACTOR_ROOT="${EXTRACTOR_ROOT:-/home/graham/workspace/experiments/extractor}"
FIXTURE_DIR="${EXTRACTOR_ROOT}/data/input/twins/preset_twin"

echo "=== Extractor Skill Sanity Check (Modular) ==="
echo ""

# 0. Check modular structure
echo -n "0. Modular structure... "
MODULES=(
    "extractor_skill/__init__.py"
    "extractor_skill/config.py"
    "extractor_skill/utils.py"
    "extractor_skill/pdf_extractor.py"
    "extractor_skill/pipeline_runner.py"
    "extractor_skill/structured_extractor.py"
    "extractor_skill/batch.py"
    "extractor_skill/memory_integration.py"
    "extractor_skill/toc_checker.py"
)
ALL_MODULES_EXIST=true
for mod in "${MODULES[@]}"; do
    if [[ ! -f "$SCRIPT_DIR/$mod" ]]; then
        echo "FAIL (missing $mod)"
        ALL_MODULES_EXIST=false
        break
    fi
done
if $ALL_MODULES_EXIST; then
    echo "OK (${#MODULES[@]} modules)"
fi

# 0a. Verify line counts (quality gate: all < 500 lines)
echo -n "0a. Line counts (<500)... "
MAX_LINES=0
MAX_FILE=""
for mod in "${MODULES[@]}"; do
    LINES=$(wc -l < "$SCRIPT_DIR/$mod" 2>/dev/null || echo "0")
    if [[ $LINES -gt $MAX_LINES ]]; then
        MAX_LINES=$LINES
        MAX_FILE=$mod
    fi
    if [[ $LINES -ge 500 ]]; then
        echo "FAIL ($mod has $LINES lines >= 500)"
        exit 1
    fi
done
echo "OK (max: $MAX_FILE @ ${MAX_LINES} lines)"

# 0b. Check for circular imports
echo -n "0b. Import check... "
IMPORT_CHECK=$("$EXTRACTOR_ROOT/.venv/bin/python" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
try:
    from extractor_skill import config
    from extractor_skill import utils
    from extractor_skill import pdf_extractor
    from extractor_skill import pipeline_runner
    from extractor_skill import structured_extractor
    from extractor_skill import batch
    from extractor_skill import memory_integration
    from extractor_skill import toc_checker
    print('OK')
except ImportError as e:
    print(f'FAIL: {e}')
except Exception as e:
    print(f'FAIL: {e}')
" 2>&1)
echo "$IMPORT_CHECK"
if [[ "$IMPORT_CHECK" != "OK" ]]; then
    exit 1
fi

# 1. Check extractor project exists
echo -n "1. Extractor project... "
if [[ ! -d "$EXTRACTOR_ROOT" ]]; then
    echo "FAIL (EXTRACTOR_ROOT not found: $EXTRACTOR_ROOT)"
    exit 1
fi
echo "OK"

# 2. Check virtual environment
echo -n "2. Virtual environment... "
PYTHON="${EXTRACTOR_ROOT}/.venv/bin/python"
if [[ ! -f "$PYTHON" ]]; then
    echo "FAIL (venv not found at $EXTRACTOR_ROOT/.venv)"
    exit 1
fi
export PYTHONPATH="${EXTRACTOR_ROOT}/src:${SCRIPT_DIR}:${PYTHONPATH}"
echo "OK"

# 3. Check fixtures exist
echo -n "3. Test fixtures... "
if [[ ! -d "$FIXTURE_DIR" ]]; then
    echo "FAIL (fixtures not found: $FIXTURE_DIR)"
    exit 1
fi
echo "OK ($FIXTURE_DIR)"

# 4. Test structured formats (fast path)
echo ""
echo "Testing structured formats (fast path)..."

FORMATS=("html" "md" "xml" "rst" "docx" "pptx" "epub")
PASS=0
FAIL=0

for fmt in "${FORMATS[@]}"; do
    FILE="${FIXTURE_DIR}/preset_twin.${fmt}"
    echo -n "  ${fmt^^}: "

    if [[ ! -f "$FILE" ]]; then
        echo "SKIP (no fixture)"
        continue
    fi

    START=$(date +%s)
    RESULT=$("$PYTHON" "$SCRIPT_DIR/extract.py" "$FILE" 2>&1)
    EXIT_CODE=$?
    END=$(date +%s)
    ELAPSED=$((END - START))

    if [[ $EXIT_CODE -eq 0 ]] && echo "$RESULT" | grep -q '"success": true'; then
        BLOCKS=$(echo "$RESULT" | grep -o '"blocks"' | wc -l || echo "?")
        echo "OK (${ELAPSED}s)"
        ((PASS++))
    else
        echo "FAIL (exit=$EXIT_CODE)"
        ((FAIL++))
    fi
done

# 5. Test spreadsheet (expected low parity)
echo ""
echo -n "  XLSX (spreadsheet): "
FILE="${FIXTURE_DIR}/preset_twin.xlsx"
if [[ -f "$FILE" ]]; then
    START=$(date +%s)
    RESULT=$("$PYTHON" "$SCRIPT_DIR/extract.py" "$FILE" 2>&1)
    EXIT_CODE=$?
    END=$(date +%s)
    ELAPSED=$((END - START))

    if [[ $EXIT_CODE -eq 0 ]] && echo "$RESULT" | grep -q '"success": true'; then
        echo "OK (${ELAPSED}s, low parity expected)"
        ((PASS++))
    else
        echo "FAIL (exit=$EXIT_CODE)"
        ((FAIL++))
    fi
else
    echo "SKIP (no fixture)"
fi

# 6. Test PDF fast mode
echo ""
echo "Testing PDF (pipeline path)..."
FILE="${FIXTURE_DIR}/preset_twin.pdf"
echo -n "  PDF --fast: "
if [[ -f "$FILE" ]]; then
    START=$(date +%s.%N)
    RESULT=$("$PYTHON" "$SCRIPT_DIR/extract.py" "$FILE" --fast 2>&1)
    EXIT_CODE=$?
    END=$(date +%s.%N)
    ELAPSED=$(echo "$END - $START" | bc)

    if [[ $EXIT_CODE -eq 0 ]] && echo "$RESULT" | grep -q '"success": true'; then
        echo "OK (${ELAPSED}s)"
        ((PASS++))
    else
        echo "FAIL (exit=$EXIT_CODE)"
        ((FAIL++))
    fi
else
    echo "SKIP (no fixture)"
fi

# 7. Test image (expected low parity without VLM)
echo ""
echo -n "  PNG (image): "
FILE="${FIXTURE_DIR}/preset_twin.png"
if [[ -f "$FILE" ]]; then
    START=$(date +%s)
    RESULT=$("$PYTHON" "$SCRIPT_DIR/extract.py" "$FILE" 2>&1)
    EXIT_CODE=$?
    END=$(date +%s)
    ELAPSED=$((END - START))

    if [[ $EXIT_CODE -eq 0 ]] && echo "$RESULT" | grep -q '"success": true'; then
        echo "OK (${ELAPSED}s, requires VLM for text)"
        ((PASS++))
    else
        echo "FAIL (exit=$EXIT_CODE)"
        ((FAIL++))
    fi
else
    echo "SKIP (no fixture)"
fi

# Summary
echo ""
echo "============================================================"
TOTAL=$((PASS + FAIL))
if [[ $FAIL -eq 0 ]]; then
    echo "SANITY CHECK COMPLETE: ${PASS}/${TOTAL} formats passed"
    echo "============================================================"
    exit 0
else
    echo "SANITY CHECK FAILED: ${PASS}/${TOTAL} passed, ${FAIL} failed"
    echo "============================================================"
    exit 1
fi
