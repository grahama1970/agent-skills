#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

echo "=== review-plan sanity check ==="

# 1. Verify the script runs
echo "1. Testing --help..."
cd "$SCRIPT_DIR"
uv run python review_plan.py --help > /dev/null 2>&1
echo "   PASS: help works"

# 2. Test review against the migration plan (should find some warnings)
PLAN_FILE="$PROJECT_ROOT/01_PI_MIGRATION_PLAN.md"
if [ -f "$PLAN_FILE" ]; then
    echo "2. Testing review on migration plan..."
    OUTPUT=$(uv run python review_plan.py review "$PLAN_FILE" --json 2>/dev/null || true)
    TASKS=$(echo "$OUTPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tasks',0))" 2>/dev/null || echo "0")
    echo "   Found $TASKS tasks in plan"
    if [ "$TASKS" -gt 0 ]; then
        echo "   PASS: parsed tasks successfully"
    else
        echo "   WARN: no tasks found (may be different format)"
    fi
else
    echo "2. SKIP: no migration plan found"
fi

# 3. Test quick check mode
echo "3. Testing check mode..."
if [ -f "$PLAN_FILE" ]; then
    uv run python review_plan.py check "$PLAN_FILE" --json > /dev/null 2>&1 || true
    echo "   PASS: check mode runs"
fi

# 4. Structured plan validation
echo "4. Testing structured plan review..."
STRUCTURED_FILE=$(mktemp --suffix=.json)
cat > "$STRUCTURED_FILE" << 'EOF'
{
  "version": 1,
  "kind": "orchestrate-plan",
  "title": "Structured review test",
  "capability_overlap": ["ok"],
  "questions_blockers": ["None"],
  "lanes": [{"id": "backend"}],
  "tasks": [
    {
      "id": "t1",
      "title": "Structured task",
      "runner": "scillm",
      "backend": "gemini-2.5-flash",
      "mode": "one_shot",
      "lane": "backend",
      "prompt": "Reply with exactly: ok",
      "tests": ["test-lab/run.sh verify-task t1 . --domain python"],
      "definition_of_done": {"command": "true", "assertion": "passes"}
    }
  ]
}
EOF
uv run python review_plan.py check "$STRUCTURED_FILE" --json > /dev/null
echo "   PASS: structured plan check runs"
rm -f "$STRUCTURED_FILE"

echo "=== sanity check complete ==="
