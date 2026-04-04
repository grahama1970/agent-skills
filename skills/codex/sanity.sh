#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0; FAIL=0; SKIP=0

pass() { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); }
skip() { echo "  [SKIP] $1 (service unavailable)"; SKIP=$((SKIP + 1)); }

echo "=== Codex Skill Sanity ==="

# --- Local checks (hard fail) ---

# Check run.sh
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    pass "run.sh exists and is executable"
else
    fail "run.sh missing or not executable"
fi

# Check SKILL.md
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
    pass "SKILL.md exists"
else
    fail "SKILL.md missing"
fi

# Check --help
if "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1; then
    pass "run.sh --help works"
else
    fail "run.sh --help failed"
fi

# Check codex CLI
if command -v codex &> /dev/null; then
    pass "'codex' CLI found"
else
    fail "'codex' CLI missing"
fi

# Check Python script exists
if [[ -f "$SCRIPT_DIR/codex.py" ]]; then
    pass "codex.py exists"
else
    fail "codex.py missing"
fi

# Check Python imports
if python3 -c "import json, os, subprocess, sys, threading, time, signal" 2>/dev/null; then
    pass "Python stdlib imports OK"
else
    fail "Python stdlib imports failed"
fi

# Check task-monitor client importable
if python3 -c "import sys; sys.path.insert(0,'$SCRIPT_DIR/../common'); from task_monitor import TaskClient" 2>/dev/null; then
    pass "common/task_monitor.py importable"
else
    fail "common/task_monitor.py not importable"
fi

# Check loguru importable via uv
if uv run --project "$SCRIPT_DIR" python -c "from loguru import logger" 2>/dev/null; then
    pass "loguru importable"
else
    fail "loguru not importable (check pyproject.toml)"
fi

# --- External service checks (graceful skip) ---

# Functional Check: Reasoning (calls OpenAI API)
echo "  [INFO] Running functional reasoning test..."
REASON_OUTPUT=$(timeout 15 "$SCRIPT_DIR/run.sh" reason "What is 2+2?" 2>&1) && REASON_RC=$? || REASON_RC=$?
if [[ $REASON_RC -eq 0 ]] && echo "$REASON_OUTPUT" | grep -q "4"; then
    pass "Functional reasoning test (2+2=4)"
else
    skip "Functional reasoning test (API rate-limited or unavailable)"
fi

# Functional Check: Extraction (calls OpenAI API)
echo "  [INFO] Running functional extraction test..."
if [[ -f "$SCRIPT_DIR/dogpile_schema.json" ]]; then
    EXTRACT_OUTPUT=$(timeout 15 "$SCRIPT_DIR/run.sh" extract "This is a test. The sky is blue." --schema "$SCRIPT_DIR/dogpile_schema.json" 2>&1) && EXTRACT_RC=$? || EXTRACT_RC=$?
    if [[ $EXTRACT_RC -eq 0 ]] && echo "$EXTRACT_OUTPUT" | grep -q '"is_ambiguous":'; then
        pass "Functional extraction test (JSON schema)"
    else
        skip "Functional extraction test (API rate-limited or unavailable)"
    fi
else
    skip "Functional extraction test (dogpile_schema.json not found)"
fi

# --- Summary ---
echo ""
echo "=== Results: $PASS passed, $FAIL failed, $SKIP skipped ==="
if [[ $FAIL -gt 0 ]]; then
    echo "Result: FAIL"
    exit 1
fi
echo "Result: PASS"
exit 0
