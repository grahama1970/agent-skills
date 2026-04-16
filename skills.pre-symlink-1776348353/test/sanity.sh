#!/usr/bin/env bash
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

check() {
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== test sanity ==="

# Check required files
check "SKILL.md exists" test -f "$SKILL_DIR/SKILL.md"
check "run.sh exists" test -f "$SKILL_DIR/run.sh"
check "test_runner.py exists" test -f "$SKILL_DIR/test_runner.py"
check "pyproject.toml exists" test -f "$SKILL_DIR/pyproject.toml"

# Check uv available
if command -v uv >/dev/null 2>&1; then
    echo "  PASS: uv available"
    PASS=$((PASS + 1))
else
    echo "  FAIL: uv available"
    FAIL=$((FAIL + 1))
fi

# Check Python imports parse
check "test_runner.py parses" python3 -c "
import ast, sys
with open('$SKILL_DIR/test_runner.py') as f:
    ast.parse(f.read())
"

# Check imports available
check "typer importable" uv run --project "$SKILL_DIR" python -c "import typer"
check "rich importable" uv run --project "$SKILL_DIR" python -c "import rich"
check "loguru importable" uv run --project "$SKILL_DIR" python -c "import loguru"

# Self-test: detect own runners
check "detect own sanity.sh" uv run --project "$SKILL_DIR" python -c "
import sys; sys.path.insert(0, '$SKILL_DIR')
from test_runner import detect_runners
from pathlib import Path
runners = detect_runners(Path('$SKILL_DIR'))
assert 'sanity' in runners, f'Expected sanity in {runners}'
"

echo ""
echo "Results: $PASS passed, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
echo "=== test sanity PASSED ==="
