#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== ingest-doc sanity check ==="

echo "[1/2] Testing Python imports..."
if uv run --project "$SCRIPT_DIR" python -c "import ingest_compliance; print('  ok')" 2>/dev/null; then
    echo "  PASS"
else
    echo "  FAIL"
    exit 1
fi

echo "[2/2] Testing status command..."
if ./run.sh status 2>&1 | grep -qi "pipeline\|skill\|status"; then
    echo "  PASS"
else
    echo "  FAIL"
    exit 1
fi

echo ""
echo "=== sanity check PASSED ==="
exit 0
