#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== cmmc-assessor sanity check ==="

echo "[1/3] Testing Python imports..."
if uv run --project "$SCRIPT_DIR" python -c "import cmmc_assessor; print('  ok imports')" 2>/dev/null; then
    echo "  PASS"
else
    echo "  FAIL: cmmc_assessor import failed"
    exit 1
fi

echo "[2/3] Testing families command..."
if ./run.sh families 2>&1 | grep -q "AC"; then
    echo "  PASS"
else
    echo "  FAIL: families command broken"
    exit 1
fi

echo "[3/3] Testing controls list..."
COUNT=$(./run.sh controls 2>&1 | wc -l)
if [ "$COUNT" -ge 100 ]; then
    echo "  PASS: $COUNT controls listed"
else
    echo "  FAIL: expected 110+ controls, got $COUNT"
    exit 1
fi

echo ""
echo "=== sanity check PASSED ==="
exit 0
