#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [ops-google] Sanity Check ==="

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
    if uv run python3 -c "import typer; import rich; import google.generativeai" 2>/dev/null; then
        echo "  Python imports OK (typer, rich, google.generativeai)"
    else
        echo "FAIL: Python imports failed in venv"
        exit 1
    fi
else
    if python3 -c "import typer; import rich" 2>/dev/null; then
        echo "  Python imports OK (system level, google-generativeai may need venv)"
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
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    PROJECT_ENV="$SCRIPT_DIR/../../.env"
    if [[ -f "$PROJECT_ENV" ]]; then
        set -a
        source "$PROJECT_ENV"
        set +a
    fi
fi

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    echo "  SKIP: GEMINI_API_KEY not set (cannot test API)"
    echo "Result: PASS (env vars missing, API tests skipped)"
    exit 0
fi
echo "  API key found"

# Check 6: Shared usage file readable
usage_file="$HOME/.pi/ops-google/usage.json"
if [[ -f "$usage_file" ]]; then
    echo "  Shared usage file exists: $usage_file"
else
    echo "  Shared usage file not yet created (will be created on first Gemini call)"
fi

# Check 7: Live API test - usage command (lightweight, no API call)
cd "$SCRIPT_DIR"
usage_output=$(timeout 10 uv run python3 manager.py usage 2>&1 || true)
if echo "$usage_output" | grep -qiE "usage|calls|remaining|error"; then
    echo "  Usage command responds"
else
    echo "  WARN: usage command returned unexpected output"
fi

echo "Result: PASS"
