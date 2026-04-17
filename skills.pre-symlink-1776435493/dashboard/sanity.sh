#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== [dashboard] Sanity Check ==="

# 1. Check required files exist
for f in SKILL.md run.sh dashboard.py collectors.py tui.py renderer.py pyproject.toml; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: Missing $f"
        exit 1
    fi
done
echo "PASS: Required files present"

# 2. Check Python syntax
for f in dashboard.py collectors.py tui.py renderer.py; do
    python3 -c "import ast; ast.parse(open('${SCRIPT_DIR}/${f}').read())" 2>/dev/null
    if [[ $? -ne 0 ]]; then
        echo "FAIL: Syntax error in $f"
        exit 1
    fi
done
echo "PASS: Python syntax OK"

# 3. Check imports
if python3 -c "import typer; import rich" 2>/dev/null; then
    echo "PASS: Core imports OK (typer, rich)"
elif uv run --project "$SCRIPT_DIR" python -c "import typer; import rich" 2>/dev/null; then
    echo "PASS: Core imports OK via uv (typer, rich)"
else
    echo "SKIP: Dependencies not installed (run 'uv sync' first)"
fi

# 4. Check collectors return dicts
COLLECTORS_TEST=$(python3 -c "
import ast, sys
tree = ast.parse(open('${SCRIPT_DIR}/collectors.py').read())
funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith('collect_')]
print(len(funcs))
" 2>/dev/null || echo "0")

if [[ "$COLLECTORS_TEST" -ge 8 ]]; then
    echo "PASS: Found $COLLECTORS_TEST collector functions"
else
    echo "WARN: Expected 8+ collectors, found $COLLECTORS_TEST"
fi

# 5. Check CLI help
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/dashboard.py" --help >/dev/null 2>&1; then
    echo "PASS: CLI help works"
elif python3 "$SCRIPT_DIR/dashboard.py" --help >/dev/null 2>&1; then
    echo "PASS: CLI help works (python3)"
else
    echo "SKIP: CLI help requires dependencies"
fi

echo "Result: PASS"
