#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/ingest-code-sanity-venv}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/ingest-code-sanity-pycache}"
UV_PYTHON=(uv run --no-project --isolated --with typer --with httpx --with loguru --with python-dotenv python)

echo "=== [ingest-code] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh ingest_code.py; do
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

# Check 3: Python source syntax valid
echo -n "Check 3: Python source syntax... "
if ! "${UV_PYTHON[@]}" -c "import py_compile; [py_compile.compile(path, doraise=True) for path in ['$SCRIPT_DIR/ingest_code.py', '$SCRIPT_DIR/code_graph_artifact.py', '$SCRIPT_DIR/code_analysis_handoff.py', '$SCRIPT_DIR/debug_affordance.py', '$SCRIPT_DIR/scripts/prove_debug_affordances.py']]" 2>/dev/null; then
    echo "FAIL - syntax error"
    exit 1
fi
echo "OK"

# Check 4: Typer import (the CLI dependency)
echo -n "Check 4: Typer import... "
if ! "${UV_PYTHON[@]}" -c "import typer; print(f'typer={typer.__version__}', end='')" 2>/dev/null; then
    echo "FAIL - typer not available"
    exit 1
fi
echo " OK"

# Check 5: Smoke test - dry run scan on this skill directory itself
echo -n "Check 5: Dry-run scan smoke test... "
cd "$SCRIPT_DIR"
"${UV_PYTHON[@]}" ingest_code.py scan "$SCRIPT_DIR" --dry-run --glob "*.py" >/tmp/ingest-code-sanity-dry-run.log 2>&1
echo "OK"

# Check 6: taxonomy skill check (optional dependency)
echo -n "Check 6: taxonomy skill... "
tax_paths=(
    "$SCRIPT_DIR/../taxonomy/taxonomy.py"
    "$SCRIPT_DIR/../taxonomy/taxonomy.py"
    "$HOME/.agents/skills/taxonomy/taxonomy.py"
)
found=false
for tp in "${tax_paths[@]}"; do
    if [[ -f "$tp" ]]; then
        found=true
        echo "OK ($tp)"
        break
    fi
done
if ! $found; then
    echo "SKIP - taxonomy module not found (CWE extraction will be limited)"
fi

echo "Result: PASS"
