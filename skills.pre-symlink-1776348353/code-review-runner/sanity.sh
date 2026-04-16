#!/usr/bin/env bash
# Sanity checks for /code-review-runner
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

check() {
    local name="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS: $name"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $name"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== /code-review-runner sanity checks ==="

# Structure checks
check "SKILL.md exists" test -f "$SCRIPT_DIR/SKILL.md"
check "run.sh exists" test -f "$SCRIPT_DIR/run.sh"
check "run.sh executable" test -x "$SCRIPT_DIR/run.sh"
check "pyproject.toml exists" test -f "$SCRIPT_DIR/pyproject.toml"
check "code_review_runner.py exists" test -f "$SCRIPT_DIR/code_review_runner.py"
check "models.py exists" test -f "$SCRIPT_DIR/models.py"
check "validators.py exists" test -f "$SCRIPT_DIR/validators.py"

# Import checks
check "models.py compiles" python3 -c "compile(open('$SCRIPT_DIR/models.py').read(), 'models.py', 'exec')"
check "validators.py compiles" python3 -c "compile(open('$SCRIPT_DIR/validators.py').read(), 'validators.py', 'exec')"
check "code_review_runner.py compiles" python3 -c "compile(open('$SCRIPT_DIR/code_review_runner.py').read(), 'code_review_runner.py', 'exec')"

# SKILL.md frontmatter
check "SKILL.md has frontmatter" grep -q "^---" "$SCRIPT_DIR/SKILL.md"
check "SKILL.md has name" grep -q "^name:" "$SCRIPT_DIR/SKILL.md"
check "SKILL.md has triggers" grep -q "^triggers:" "$SCRIPT_DIR/SKILL.md"
check "SKILL.md has description" grep -q "^description:" "$SCRIPT_DIR/SKILL.md"

# Dependency checks
# These can't use check() because ! negation doesn't work in "$@"
if grep -rq "^import logging" "$SCRIPT_DIR"/code_review_runner.py 2>/dev/null; then
    echo "  FAIL: no import logging"; FAIL=$((FAIL + 1))
else
    echo "  PASS: no import logging"; PASS=$((PASS + 1))
fi
if grep -rq "^import requests" "$SCRIPT_DIR"/code_review_runner.py 2>/dev/null; then
    echo "  FAIL: no import requests"; FAIL=$((FAIL + 1))
else
    echo "  PASS: no import requests"; PASS=$((PASS + 1))
fi
check "uses loguru" grep -rq "from loguru" "$SCRIPT_DIR"/*.py
check "uses httpx" grep -rq "import httpx" "$SCRIPT_DIR"/*.py
check "uses pydantic" grep -rq "from pydantic" "$SCRIPT_DIR"/*.py
check "uses typer" grep -rq "import typer" "$SCRIPT_DIR"/*.py

# Dry-run test (creates temp spec, runs T0 only)
TMPSPEC=$(mktemp /tmp/crr-sanity-XXXXXX.json)
cat > "$TMPSPEC" <<'EOF'
{
  "task_id": "sanity-test",
  "files": ["code_review_runner.py", "models.py", "validators.py"],
  "cwd": "SCRIPT_DIR_PLACEHOLDER",
  "backend": "codex",
  "max_rounds": 1
}
EOF
sed -i "s|SCRIPT_DIR_PLACEHOLDER|$SCRIPT_DIR|" "$TMPSPEC"

check "dry-run succeeds" uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/code_review_runner.py" dry-run "$TMPSPEC"
rm -f "$TMPSPEC"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"
exit $FAIL
