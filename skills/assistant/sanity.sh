#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [assistant] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh assistant.py model_registry.json harvest.py pyproject.toml; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL - missing $f"
        exit 1
    fi
done
echo "OK"

# Check 2: uv available
echo -n "Check 2: uv available... "
if ! command -v uv &>/dev/null; then
    echo "FAIL - uv not found"
    exit 1
fi
echo "OK"

# Check 3: Python syntax validation
echo -n "Check 3: Python syntax (assistant.py)... "
if ! python3 -m py_compile "$SCRIPT_DIR/assistant.py" 2>/dev/null; then
    echo "FAIL - syntax error in assistant.py"
    exit 1
fi
echo "OK"

echo -n "Check 4: Python syntax (harvest.py)... "
if ! python3 -m py_compile "$SCRIPT_DIR/harvest.py" 2>/dev/null; then
    echo "FAIL - syntax error in harvest.py"
    exit 1
fi
echo "OK"

# Check 5: Core imports
echo -n "Check 5: Core Python imports... "
if ! python3 -c "import json, hashlib, time, sys, os; print('OK', end='')" 2>/dev/null; then
    echo "FAIL - missing stdlib imports"
    exit 1
fi
echo ""

# Check 6: Registry loads
echo -n "Check 6: Registry JSON valid... "
if ! python3 -c "
import json
with open('$SCRIPT_DIR/model_registry.json') as f:
    reg = json.load(f)
assert 'validators' in reg, 'missing validators'
assert 'classifiers' in reg, 'missing classifiers'
print('OK', end='')
" 2>/dev/null; then
    echo "FAIL - invalid model_registry.json"
    exit 1
fi
echo ""

# Check 7: run.sh is executable
echo -n "Check 7: run.sh executable... "
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL - run.sh not executable"
    exit 1
fi
echo "OK"

# Check 8: Sibling skill dependencies exist
echo -n "Check 8: Sibling skills... "
MISSING=""
for skill in create-gpt create-classifier scillm common; do
    if [[ ! -d "$SCRIPT_DIR/../$skill" ]]; then
        MISSING="$MISSING $skill"
    fi
done
if [[ -n "$MISSING" ]]; then
    echo "WARN - missing sibling skills:$MISSING (gateway will use passthrough mode)"
else
    echo "OK"
fi

echo ""
echo "Result: PASS"
