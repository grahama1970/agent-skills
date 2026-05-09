#!/bin/bash
# Sanity check for plan skill
# Verifies the skill can run and validate task files

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Plan Skill Sanity Check ==="

# Check Python availability
if command -v uv &> /dev/null; then
    EXEC=(uv run --project "$SCRIPT_DIR" python)
    echo "[OK] uv available"
elif command -v python3 &> /dev/null; then
    EXEC=(python3)
    echo "[OK] python3 available"
else
    echo "[FAIL] No Python interpreter found"
    exit 1
fi

# Check plan.py exists and is valid Python
if [ ! -f "$SCRIPT_DIR/plan.py" ]; then
    echo "[FAIL] plan.py not found"
    exit 1
fi

"${EXEC[@]}" -m py_compile "$SCRIPT_DIR/plan.py"
echo "[OK] plan.py syntax valid"

# Create a structured test task file and validate it
TEST_FILE=$(mktemp --suffix=.yaml)
cat > "$TEST_FILE" << EOF
version: 1
kind: orchestrate-plan
repo_root: "$SCRIPT_DIR"
metadata:
  title: "Plan sanity"
  goal: "Validate the /plan contract"
capability_overlap:
  - "sanity.sh validates the modern structured-plan path"
questions_blockers:
  - "None"
lanes:
  - id: "0"
    label: "Sanity"
tasks:
  - id: "1"
    title: "Run deterministic sanity command"
    lane: "0"
    runner: "local"
    backend: ""
    mode: ""
    command: "true"
    tests:
      - "true"
    definition_of_done:
      command: "true"
      assertion: "exit_code == 0"
EOF

VALIDATION=$("${EXEC[@]}" "$SCRIPT_DIR/plan.py" --validate "$TEST_FILE" --json)

if echo "$VALIDATION" | grep -q '"valid": true'; then
    echo "[OK] Task file validation works"
else
    echo "[FAIL] Task file validation failed"
    echo "$VALIDATION"
    exit 1
fi

# Test markdown -> structured conversion
STRUCTURED_JSON=$("${EXEC[@]}" "$SCRIPT_DIR/plan.py" --convert "$TEST_FILE" --format json)
if echo "$STRUCTURED_JSON" | grep -q '"kind": "orchestrate-plan"'; then
    echo "[OK] Structured conversion works"
else
    echo "[FAIL] Structured conversion failed"
    exit 1
fi

rm -f "$TEST_FILE"

echo ""
echo "=== All sanity checks passed ==="
exit 0
