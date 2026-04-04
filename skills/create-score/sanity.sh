#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [create-score] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh pyproject.toml; do
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

# Check 3: Docker available (needed for ACE-Step)
echo -n "Check 3: Docker available... "
if command -v docker &>/dev/null; then
    echo "OK"
else
    echo "SKIP - docker not found (required for ACE-Step service)"
fi

# Check 4: Python imports (typer, httpx, pydantic, loguru)
echo -n "Check 4: Python imports... "
cd "$SCRIPT_DIR"
if ! uv run --project "$SCRIPT_DIR" python -c "
import typer
import httpx
import pydantic
from loguru import logger
print('OK', end='')
" 2>/dev/null; then
    echo "FAIL - missing Python dependencies"
    exit 1
fi
echo ""

# Check 5: create_score module importable
echo -n "Check 5: create_score module import... "
cd "$SCRIPT_DIR"
if ! uv run --project "$SCRIPT_DIR" python -c "from create_score import cli; print('OK', end='')" 2>/dev/null; then
    echo "FAIL - create_score module not importable"
    exit 1
fi
echo ""

# Check 6: CLI help works
echo -n "Check 6: run.sh help... "
output=$("$SCRIPT_DIR/run.sh" help 2>&1 || true)
if echo "$output" | grep -qi "generate\|score\|ace"; then
    echo "OK"
else
    echo "FAIL - run.sh help did not produce expected output"
    exit 1
fi

echo "Result: PASS"
