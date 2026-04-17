#!/usr/bin/env bash
# Sanity checks for analytics skill

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== analytics Sanity Checks ==="
echo ""

# Ensure dependencies
if ! command -v uv &>/dev/null; then
    echo "FAIL: uv not found"
    exit 1
fi

if [[ ! -d ".venv" ]]; then
    echo "Installing dependencies..."
    uv sync --quiet
fi

FAIL=0

# Test 1: Pandas import
echo "1. Pandas import..."
if uv run python -c "import pandas; print(f'   pandas {pandas.__version__}')"; then
    echo "   PASS"
else
    echo "   FAIL"
    FAIL=1
fi

# Test 2: CLI import
echo ""
echo "2. CLI imports..."
if uv run python -c "from src.cli import app; print('   Imports OK')"; then
    echo "   PASS"
else
    echo "   FAIL"
    FAIL=1
fi

# Test 3: Insights module
echo ""
echo "3. Insights module..."
if uv run python -c "
from src.insights import generate_insights, format_for_horus
print('   Functions available')
"; then
    echo "   PASS"
else
    echo "   FAIL"
    FAIL=1
fi

# Test 4: Test with sample data if available
echo ""
echo "4. Test with real data..."
HISTORY_FILE="$HOME/.pi/ingest-yt-history/history.jsonl"
if [[ -f "$HISTORY_FILE" ]]; then
    if uv run python -c "
from src.insights import generate_insights
result = generate_insights('$HISTORY_FILE')
print(f'   Total items: {result[\"summary\"][\"total_items\"]}')
print(f'   Date range: {result[\"summary\"][\"date_range\"].get(\"start\", \"?\")} to {result[\"summary\"][\"date_range\"].get(\"end\", \"?\")}')
"; then
        echo "   PASS"
    else
        echo "   FAIL"
        FAIL=1
    fi
else
    echo "   SKIP: No history data at $HISTORY_FILE"
fi

echo ""
echo "======================================="
if [[ $FAIL -eq 0 ]]; then
    echo "All sanity checks PASSED"
    exit 0
else
    echo "Some checks FAILED"
    exit 1
fi
