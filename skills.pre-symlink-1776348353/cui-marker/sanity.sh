#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== cui-marker sanity check ==="

echo "[1/3] Testing Python imports..."
if uv run --project "$SCRIPT_DIR" python -c "import cui_marker; print('  ok')" 2>/dev/null; then
    echo "  PASS"
else
    echo "  FAIL"
    exit 1
fi

echo "[2/3] Testing categories command..."
if ./run.sh categories 2>&1 | grep -q "CTI"; then
    echo "  PASS"
else
    echo "  FAIL"
    exit 1
fi

echo "[3/3] Testing scan on sample text..."
RESULT=$(echo "This document contains ITAR controlled technical data per DFARS 252.204-7012" | ./run.sh scan --stdin 2>&1)
if echo "$RESULT" | grep -qi "cui\|CTI\|EXPT"; then
    echo "  PASS"
else
    echo "  FAIL: no CUI detected in ITAR sample"
    exit 1
fi

echo ""
echo "=== sanity check PASSED ==="
exit 0
