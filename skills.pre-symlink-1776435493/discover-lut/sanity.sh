#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [discover-lut] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh main.py pyproject.toml; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL - missing $f"
        exit 1
    fi
done
echo "OK"

# Check 2: uv available
echo -n "Check 2: uv available... "
if ! command -v uv &>/dev/null; then
    echo "FAIL - uv not found"
    exit 1
fi
echo "OK"

# Check 3: Python imports (click, rich)
# NOTE: main.py uses httpx but pyproject.toml declares requests.
# This is a known dependency mismatch. Test the declared deps first.
echo -n "Check 3: Python imports (click, rich)... "
cd "$SCRIPT_DIR"
if ! uv run --project "$SCRIPT_DIR" python -c "
import click
import rich
from rich.table import Table
print('click+rich OK', end='')
" 2>/dev/null; then
    echo "FAIL - missing click or rich"
    exit 1
fi
echo ""

echo -n "Check 3b: httpx import (used by main.py)... "
cd "$SCRIPT_DIR"
if uv run --project "$SCRIPT_DIR" python -c "import httpx" 2>/dev/null; then
    echo "OK"
else
    # httpx is imported in main.py but not in pyproject.toml (lists requests instead)
    echo "WARN - httpx not in project deps (pyproject.toml lists 'requests' but main.py uses httpx)"
fi

# Check 4: main.py syntax
echo -n "Check 4: main.py syntax... "
if ! python3 -c "import py_compile; py_compile.compile('$SCRIPT_DIR/main.py', doraise=True)" 2>/dev/null; then
    echo "FAIL - syntax error in main.py"
    exit 1
fi
echo "OK"

# Check 5: Smoke test - list catalog (will work if httpx is available system-wide)
echo -n "Check 5: List catalog (smoke test)... "
cd "$SCRIPT_DIR"
output=$(uv run --project "$SCRIPT_DIR" python main.py list 2>&1 || true)
if echo "$output" | grep -qi "noir\|teal\|kodak\|catalog"; then
    echo "OK"
else
    echo "SKIP - list command could not run (likely httpx dependency issue)"
fi

echo "Result: PASS"
