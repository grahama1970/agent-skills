#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [discover-talent] Sanity Check ==="

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

# Check 3: Python imports (httpx, dotenv, rich, typer)
echo -n "Check 3: Python imports... "
cd "$SCRIPT_DIR"
if ! uv run python -c "
import httpx
import dotenv
import rich
import typer
print('OK', end='')
" 2>/dev/null; then
    echo "FAIL - missing Python dependencies"
    exit 1
fi
echo ""

# Check 4: discover_talent module importable
echo -n "Check 4: discover_talent module import... "
cd "$SCRIPT_DIR"
if ! uv run python -c "from discover_talent import cli; print('OK', end='')" 2>/dev/null; then
    echo "FAIL - discover_talent module not importable"
    exit 1
fi
echo ""

# Check 5: TMDB_API_KEY check
echo -n "Check 5: TMDB_API_KEY... "
if [[ -n "${TMDB_API_KEY:-}" ]]; then
    echo "OK (set)"
else
    # Also check .env file
    if [[ -f "$SCRIPT_DIR/.env" ]] && grep -q "TMDB_API_KEY" "$SCRIPT_DIR/.env" 2>/dev/null; then
        echo "OK (found in .env)"
    else
        echo "SKIP - TMDB_API_KEY not set (required for API calls)"
    fi
fi

# Check 6: CLI help works
echo -n "Check 6: CLI help... "
output=$("$SCRIPT_DIR/run.sh" help 2>&1 || true)
if echo "$output" | grep -qi "discover-talent\|search\|filmography"; then
    echo "OK"
else
    echo "FAIL - run.sh help did not produce expected output"
    exit 1
fi

# Check 7: Live API check (only if key is available)
echo -n "Check 7: TMDB API connectivity... "
if [[ -n "${TMDB_API_KEY:-}" ]]; then
    cd "$SCRIPT_DIR"
    output=$(uv run python -m discover_talent.cli check 2>&1 || true)
    if echo "$output" | grep -qi "ok\|success\|connected"; then
        echo "OK"
    else
        echo "WARN - API check returned unexpected response"
    fi
else
    echo "SKIP - no TMDB_API_KEY"
fi

echo "Result: PASS"
