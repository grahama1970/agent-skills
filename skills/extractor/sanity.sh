#!/bin/bash
# Sanity check for extractor skill
# Verifies that all supported formats extract correctly
# Note: We don't use 'set -e' because ((PASS++)) returns false when PASS=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRACTOR_ROOT="${EXTRACTOR_ROOT:-/home/graham/workspace/experiments/extractor}"
FIXTURE_DIR="${EXTRACTOR_ROOT}/data/input/twins/preset_twin"

echo "=== Extractor Skill Sanity Check ==="
echo ""

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
export PYTHONPATH="${EXTRACTOR_ROOT}/src:${PYTHONPATH}"
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
