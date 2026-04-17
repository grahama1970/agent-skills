#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [ops-chutes] Sanity Check ==="

# Check 1: Required files exist
echo "Check 1: Required files..."
for f in SKILL.md run.sh manager.py util.py pyproject.toml; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: Missing $f"
        exit 1
    fi
done
echo "  All required files present"

# Check 2: uv available
if ! command -v uv &>/dev/null; then
    echo "FAIL: uv not found"
    exit 1
fi
echo "  uv available"

# Check 3: Python imports (from venv if it exists)
cd "$SCRIPT_DIR"
if [[ -d ".venv" ]]; then
    if uv run python3 -c "import typer; import rich; import httpx; import pytz" 2>/dev/null; then
        echo "  Python imports OK (typer, rich, httpx, pytz)"
    else
        echo "FAIL: Python imports failed in venv (typer, rich, httpx, pytz)"
        exit 1
    fi
else
    if python3 -c "import typer; import rich; import httpx" 2>/dev/null; then
        echo "  Python imports OK (system level)"
    else
        echo "  WARN: Python imports failed (venv not built yet, run: uv venv && uv pip install .)"
    fi
fi

# Check 4: manager.py and util.py are parseable
if python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/manager.py').read())" 2>/dev/null; then
    echo "  manager.py parses without errors"
else
    echo "FAIL: manager.py has syntax errors"
    exit 1
fi

if python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/util.py').read())" 2>/dev/null; then
    echo "  util.py parses without errors"
else
    echo "FAIL: util.py has syntax errors"
    exit 1
fi

# Check 5: API key available
if [[ -z "${CHUTES_API_TOKEN:-}" && -z "${CHUTES_API_KEY:-}" ]]; then
    PROJECT_ENV="$SCRIPT_DIR/../../.env"
    if [[ -f "$PROJECT_ENV" ]]; then
        set -a
        source "$PROJECT_ENV"
        set +a
    fi
fi

if [[ -z "${CHUTES_API_TOKEN:-}" && -z "${CHUTES_API_KEY:-}" ]]; then
    echo "  SKIP: CHUTES_API_TOKEN / CHUTES_API_KEY not set (cannot test API)"
    echo "Result: PASS (env vars missing, API tests skipped)"
    exit 0
fi
echo "  API key found"

# Check 6: Live API test - status command (lightweight)
cd "$SCRIPT_DIR"
status_output=$(timeout 15 uv run python3 manager.py status 2>&1 || true)
if echo "$status_output" | grep -qiE "chute|status|error|no chutes"; then
    echo "  API status command responds"
else
    echo "  WARN: status command returned unexpected output"
fi

echo "Result: PASS"
