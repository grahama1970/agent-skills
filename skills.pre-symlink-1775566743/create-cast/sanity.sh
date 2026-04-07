#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [create-cast] Sanity Check ==="

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

# Check 3: Core Python imports via uv
echo -n "Check 3: Python imports (httpx, yaml, rich, typer)... "
cd "$SCRIPT_DIR"
if ! uv run python -c "
import httpx
import yaml
import rich
import typer
print('OK', end='')
" 2>/dev/null; then
    echo "FAIL - missing Python dependencies"
    exit 1
fi
echo ""

# Check 4: create_cast module importable
echo -n "Check 4: create_cast module import... "
cd "$SCRIPT_DIR"
if ! uv run python -c "from create_cast import cli; print('OK', end='')" 2>/dev/null; then
    echo "FAIL - create_cast module not importable"
    exit 1
fi
echo ""

# Check 5: CLI help works
echo -n "Check 5: CLI help... "
output=$("$SCRIPT_DIR/run.sh" help 2>&1 || true)
if echo "$output" | grep -qi "create-cast\|casting"; then
    echo "OK"
else
    echo "FAIL - run.sh help did not produce expected output"
    exit 1
fi

echo "Result: PASS"
