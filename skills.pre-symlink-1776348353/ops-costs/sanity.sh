#!/usr/bin/env bash
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="$(dirname "$SKILL_DIR")"
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

echo "=== ops-costs sanity ==="

# Check required files
check "SKILL.md exists" test -f "$SKILL_DIR/SKILL.md"
check "run.sh exists" test -f "$SKILL_DIR/run.sh"
check "aggregator.py exists" test -f "$SKILL_DIR/aggregator.py"
check "pyproject.toml exists" test -f "$SKILL_DIR/pyproject.toml"

# Check uv available
if command -v uv >/dev/null 2>&1; then
    echo "  PASS: uv available"
    PASS=$((PASS + 1))
else
    echo "  FAIL: uv available"
    FAIL=$((FAIL + 1))
fi

# Check Python parses
check "aggregator.py parses" python3 -c "
import ast
with open('$SKILL_DIR/aggregator.py') as f:
    ast.parse(f.read())
"

# Check imports
check "typer importable" uv run --project "$SKILL_DIR" python -c "import typer"
check "rich importable" uv run --project "$SKILL_DIR" python -c "import rich"
check "loguru importable" uv run --project "$SKILL_DIR" python -c "import loguru"

# Check at least one provider skill exists
FOUND_PROVIDER=0
for p in ops-chutes ops-claude ops-google ops-runpod; do
    if [ -f "$SKILLS_ROOT/$p/run.sh" ]; then
        FOUND_PROVIDER=1
        break
    fi
done
if [ "$FOUND_PROVIDER" -eq 1 ]; then
    echo "  PASS: at least one provider skill found"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no provider skills found"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
echo "=== ops-costs sanity PASSED ==="
