#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [debug-fetcher] Sanity Check ==="

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

# Check 3: Python imports (typer, rich, httpx)
echo -n "Check 3: Python imports (typer, rich, httpx)... "
cd "$SCRIPT_DIR"
if ! uv run --project "$SCRIPT_DIR" python -c "
import typer
import rich
import httpx
print('OK', end='')
" 2>/dev/null; then
    echo "FAIL - missing Python dependencies"
    exit 1
fi
echo ""

# Check 4: debug_fetcher module importable
echo -n "Check 4: debug_fetcher module import... "
cd "$SCRIPT_DIR"
if ! uv run --project "$SCRIPT_DIR" python -c "from debug_fetcher import cli; print('OK', end='')" 2>/dev/null; then
    echo "FAIL - debug_fetcher module not importable"
    exit 1
fi
echo ""

# Check 5: status command works
echo -n "Check 5: status command... "
output=$("$SCRIPT_DIR/run.sh" status 2>&1 || true)
if echo "$output" | grep -q '"ok": true'; then
    echo "OK"
else
    echo "FAIL - status command did not return expected JSON"
    exit 1
fi

# Check 6: Python syntax check on package
echo -n "Check 6: Package syntax check... "
fail_count=0
for f in "$SCRIPT_DIR"/debug_fetcher/*.py; do
    [[ ! -f "$f" ]] && continue
    if ! python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
        echo ""
        echo "  WARN: syntax issue in $(basename "$f")"
        ((fail_count++)) || true
    fi
done
if [[ $fail_count -eq 0 ]]; then
    echo "OK"
else
    echo "WARN - $fail_count files with issues"
fi

echo "Result: PASS"
