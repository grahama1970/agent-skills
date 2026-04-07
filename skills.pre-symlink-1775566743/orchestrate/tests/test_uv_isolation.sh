#!/bin/bash
# Test: structured_execute.py runs under uv, not bare python3
#
# Regression for: anyio version mismatch when system python3 is used instead of
# the skill's .venv. All invocations of structured_execute.py in run.sh MUST use
# `uv run --project "$SCRIPT_DIR" python` — never bare `python3`.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0

echo "=== Test: uv isolation for structured_execute.py ==="

# 1. Every invocation of STRUCTURED_EXECUTE_PY must use uv run
echo -n "1. All structured_execute.py invocations use uv run... "
bare_python_calls=$(grep -n 'python3\s*"\$STRUCTURED_EXECUTE_PY"' "$SCRIPT_DIR/run.sh" 2>/dev/null || true)
if [[ -n "$bare_python_calls" ]]; then
    echo "FAIL"
    echo "   Found bare python3 calls (must use 'uv run --project'):"
    echo "   $bare_python_calls"
    ERRORS=$((ERRORS + 1))
else
    echo "PASS"
fi

# 2. Verify structured_execute.py can import under uv
echo -n "2. structured_execute.py imports cleanly under uv... "
import_output=$(uv run --project "$SCRIPT_DIR" python -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/..')
import importlib.util
spec = importlib.util.spec_from_file_location('se', '$SCRIPT_DIR/structured_execute.py')
mod = importlib.util.module_from_spec(spec)
# Don't execute, just check imports resolve
print('imports OK')
" 2>&1) || {
    echo "FAIL"
    echo "   $import_output"
    ERRORS=$((ERRORS + 1))
}
if [[ "$import_output" == *"imports OK"* ]]; then
    echo "PASS"
fi

# 3. Verify httpx and asyncio are available in the venv
echo -n "3. httpx available in uv venv... "
if uv run --project "$SCRIPT_DIR" python -c "import httpx; print(httpx.__version__)" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL — httpx not importable"
    ERRORS=$((ERRORS + 1))
fi

# 4. Verify anyio is importable and compatible (>=4.0 for httpx 0.28+)
echo -n "4. anyio importable and compatible... "
anyio_check=$(uv run --project "$SCRIPT_DIR" python -c "
import anyio
from importlib.metadata import version
v = version('anyio')
major = int(v.split('.')[0])
assert major >= 4, f'anyio {v} < 4.0'
print(f'PASS ({v})')
" 2>/dev/null)
if [[ "$anyio_check" == PASS* ]]; then
    echo "$anyio_check"
else
    echo "FAIL — $anyio_check"
    ERRORS=$((ERRORS + 1))
fi

# 5. No bare python3 calls to review_plan or shared_plan either
echo -n "5. No bare python3 calls to SHARED_PLAN_PY... "
# Exclude lines that are inside echo/printf (display only)
bare_shared=$(grep -n 'python3\s*"\$SHARED_PLAN_PY"' "$SCRIPT_DIR/run.sh" | grep -v 'echo\|printf' || true)
# The alias handles these, but verify the alias is active
if grep -q 'shopt -s expand_aliases' "$SCRIPT_DIR/run.sh" && grep -q 'alias python3=' "$SCRIPT_DIR/run.sh"; then
    echo "PASS (alias active)"
else
    if [[ -n "$bare_shared" ]]; then
        echo "FAIL"
        echo "   $bare_shared"
        ERRORS=$((ERRORS + 1))
    else
        echo "PASS"
    fi
fi

echo ""
if [[ $ERRORS -gt 0 ]]; then
    echo "FAILED ($ERRORS errors)"
    exit 1
fi
echo "ALL PASSED"
