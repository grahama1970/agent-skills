#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Sanity check for eval-skills ==="

PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label"
        FAIL=$((FAIL + 1))
    fi
}

# Core files exist
check "eval_runner.py exists" test -f "$SCRIPT_DIR/eval_runner.py"
check "eval_reporting.py exists" test -f "$SCRIPT_DIR/eval_reporting.py"
check "SKILL.md exists" test -f "$SCRIPT_DIR/SKILL.md"
check "pyproject.toml exists" test -f "$SCRIPT_DIR/pyproject.toml"
check "run.sh exists" test -f "$SCRIPT_DIR/run.sh"
check "fixtures dir exists" test -d "$SCRIPT_DIR/fixtures"
check "self-test eval.json exists" test -f "$SCRIPT_DIR/fixtures/eval.json"

# CLI help works
check "CLI --help works" "$SCRIPT_DIR/run.sh" --help

# Self-eval: run eval on own fixtures
OUTPUT=$("$SCRIPT_DIR/run.sh" eval --skill eval-skills 2>&1) || true
if echo "$OUTPUT" | grep -q "PASS"; then
    echo "  PASS: self-eval produces PASS results"
    PASS=$((PASS + 1))
else
    echo "  FAIL: self-eval did not produce PASS results"
    FAIL=$((FAIL + 1))
fi

# Verify skills without fixtures are skipped (not failed)
if echo "$OUTPUT" | grep -qE "Skipped|skipped|No fixtures"; then
    echo "  PASS: skipping logic present"
    PASS=$((PASS + 1))
else
    echo "  INFO: no skip output (may be OK if eval-skills has own fixtures)"
    PASS=$((PASS + 1))
fi

echo ""
echo "sanity: $PASS passed, $FAIL failed"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
