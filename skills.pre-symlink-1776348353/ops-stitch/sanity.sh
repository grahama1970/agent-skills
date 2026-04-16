#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ERRORS=0

echo "=== ops-stitch sanity ==="

# 1. Check bundle.py imports
echo -n "Import check... "
if uv run --project "$SCRIPT_DIR" python -c "import bundle" 2>/dev/null; then
    echo "OK"
else
    echo "FAIL"
    ERRORS=$((ERRORS + 1))
fi

# 2. Check --help works
echo -n "CLI help check... "
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/bundle.py" --help >/dev/null 2>&1; then
    echo "OK"
else
    echo "FAIL"
    ERRORS=$((ERRORS + 1))
fi

# 3. Check Chrome is findable
echo -n "Chrome binary check... "
if command -v google-chrome-stable >/dev/null 2>&1; then
    echo "OK"
else
    echo "WARN (google-chrome-stable not in PATH)"
fi

if [ "$ERRORS" -gt 0 ]; then
    echo "FAILED: $ERRORS errors"
    exit 1
fi

echo "All sanity checks passed."
