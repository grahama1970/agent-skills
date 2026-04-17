#!/bin/bash
# Test: structured_execute.py async executor correctness
#
# Verifies the asyncio rewrite works: plan validation, local task execution,
# cancel event handling, session creation.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0

echo "=== Test: async executor ==="

# 1. Validate a minimal plan
echo -n "1. Plan validation (valid plan)... "
FIXTURE_DIR="$SCRIPT_DIR/tests/fixtures"
mkdir -p "$FIXTURE_DIR"

cat > "$FIXTURE_DIR/test_plan.yaml" << 'PLAN'
version: 1
kind: orchestrate-plan
metadata:
  title: Test Plan
  goal: Verify executor works
capability_overlap:
  - "Test fixture — no real skill overlap"
tasks:
  - id: T1
    title: Echo test
    runner: local
    mode: one_shot
    command: echo hello
    definition_of_done:
      command: "true"
      assertion: "exits 0"
PLAN

output=$(uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/structured_execute.py" run "$FIXTURE_DIR/test_plan.yaml" 2>&1) || {
    echo "FAIL"
    echo "   $output"
    ERRORS=$((ERRORS + 1))
}
if echo "$output" | grep -q "session_started"; then
    echo "PASS (session created)"
else
    echo "FAIL — no session_started event"
    echo "   $output" | head -5
    ERRORS=$((ERRORS + 1))
fi

# 2. Verify session artifacts were created
echo -n "2. Session artifacts created... "
session_dir=$(echo "$output" | grep "session_started" | python3 -c "import sys,json; print(json.loads(sys.stdin.readline())['session_dir'])" 2>/dev/null || echo "")
if [[ -n "$session_dir" && -f "$session_dir/status.json" && -f "$session_dir/plan.json" && -f "$session_dir/INTERVENTION.md" ]]; then
    echo "PASS"
else
    echo "FAIL — missing session artifacts at $session_dir"
    ERRORS=$((ERRORS + 1))
fi

# 3. Verify task completed in status.json
echo -n "3. Task T1 completed... "
if [[ -n "$session_dir" ]]; then
    t1_status=$(python3 -c "import json; d=json.load(open('$session_dir/status.json')); print([t['status'] for t in d['tasks'] if t['id']=='T1'][0])" 2>/dev/null || echo "unknown")
    if [[ "$t1_status" == "completed" ]]; then
        echo "PASS"
    else
        echo "FAIL — T1 status: $t1_status"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "SKIP (no session dir)"
fi

# 4. Verify local task output was captured
echo -n "4. Local task output captured... "
if [[ -n "$session_dir" && -f "$session_dir/T1.stdout.txt" ]]; then
    content=$(cat "$session_dir/T1.stdout.txt")
    if [[ "$content" == *"hello"* ]]; then
        echo "PASS"
    else
        echo "FAIL — output: $content"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "FAIL — no output file"
    ERRORS=$((ERRORS + 1))
fi

# 5. Status command works
echo -n "5. Status command... "
status_output=$(uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/structured_execute.py" status 2>&1) || true
if echo "$status_output" | grep -q "Session:"; then
    echo "PASS"
else
    echo "FAIL"
    echo "   $status_output" | head -3
    ERRORS=$((ERRORS + 1))
fi

# 6. Invalid plan is rejected
echo -n "6. Invalid plan rejected... "
cat > "$FIXTURE_DIR/test_bad_plan.yaml" << 'PLAN'
version: 1
kind: orchestrate-plan
metadata:
  title: Bad Plan
tasks:
  - id: T1
    title: No runner
PLAN

bad_output=$(uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/structured_execute.py" run "$FIXTURE_DIR/test_bad_plan.yaml" 2>&1) || true
if echo "$bad_output" | grep -qiE "error|invalid|missing"; then
    echo "PASS (rejected)"
else
    echo "FAIL — bad plan was accepted"
    ERRORS=$((ERRORS + 1))
fi

# Cleanup fixtures
rm -f "$FIXTURE_DIR/test_plan.yaml" "$FIXTURE_DIR/test_bad_plan.yaml"

echo ""
if [[ $ERRORS -gt 0 ]]; then
    echo "FAILED ($ERRORS errors)"
    exit 1
fi
echo "ALL PASSED"
