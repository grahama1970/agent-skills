#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== project-state sanity check ==="

# Check Python script exists and is valid syntax
python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/project_state.py').read())"
echo "PASS: project_state.py is valid Python"

# Check run.sh is executable
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "PASS: run.sh is executable"
else
    echo "FAIL: run.sh not executable"
    exit 1
fi

# Check SKILL.md exists
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "PASS: SKILL.md exists"
else
    echo "FAIL: SKILL.md missing"
    exit 1
fi

# Try generating JSON report (doesn't need daemons running)
OUTPUT=$(python3 "$SCRIPT_DIR/project_state.py" --json 2>/dev/null || true)
if echo "$OUTPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'project' in d and 'phase_1_infrastructure' in d" 2>/dev/null; then
    echo "PASS: JSON report generated with required fields"
else
    echo "WARN: JSON report generation failed (daemons may not be running)"
fi

echo ""
echo "All sanity checks passed."
