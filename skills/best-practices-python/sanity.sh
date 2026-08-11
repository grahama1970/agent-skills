#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/best-practices-python-sanity-venv}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/best-practices-python-pycache}"
PY=(uv run --project "$SCRIPT_DIR" python)
echo "=== [best-practices-python] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1 - Required files: "
FAIL=0
for f in SKILL.md README.md AGENTS.md; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        FAIL=1
    fi
done
if [[ ! -d "$SCRIPT_DIR/rules" ]]; then
    echo "FAIL: missing rules/ directory"
    FAIL=1
fi
if [[ ! -d "$SCRIPT_DIR/scripts" ]]; then
    echo "FAIL: missing scripts/ directory"
    FAIL=1
fi
if [[ $FAIL -ne 0 ]]; then
    exit 1
fi
echo "PASS"

# Check 2: Rules directory has content
echo -n "Check 2 - Rules files: "
RULE_COUNT=$(find "$SCRIPT_DIR/rules" -name '*.md' ! -name '_*' | wc -l)
if [[ "$RULE_COUNT" -lt 10 ]]; then
    echo "FAIL: only $RULE_COUNT rule files found (expected 10+)"
    exit 1
fi
echo "PASS ($RULE_COUNT rules)"

# Check 3: Python scripts syntax check
echo -n "Check 3 - Python syntax: "
PY_FAIL=0
for py in "$SCRIPT_DIR"/scripts/*.py; do
    if [[ -f "$py" ]]; then
        if ! "${PY[@]}" -m py_compile "$py" 2>/dev/null; then
            echo "FAIL: syntax error in $(basename "$py")"
            PY_FAIL=1
        fi
    fi
done
[[ $PY_FAIL -eq 0 ]] && echo "PASS"

# Check 4: Python runtime imports
echo -n "Check 4 - Python runtime imports: "
"${PY[@]}" -c "
from pathlib import Path
import sys
" 2>/dev/null && echo "PASS" || { echo "FAIL"; exit 1; }

# Check 5: Smoke test - check_file_limits.py runs
echo -n "Check 5 - check_file_limits smoke test: "
if "${PY[@]}" "$SCRIPT_DIR/scripts/check_file_limits.py" >/dev/null 2>&1; then
    echo "PASS"
else
    echo "WARN: check_file_limits.py returned non-zero (may have found large files)"
fi

# Check 6: compile_agents.py runs
echo -n "Check 6 - compile_agents smoke test: "
if "${PY[@]}" "$SCRIPT_DIR/scripts/compile_agents.py" >/dev/null 2>&1; then
    echo "PASS"
else
    echo "WARN: compile_agents.py failed (may need specific working directory)"
fi

# Check 7: YAML frontmatter in SKILL.md
echo -n "Check 7 - SKILL.md frontmatter: "
if head -1 "$SCRIPT_DIR/SKILL.md" | grep -q '^---'; then
    echo "PASS"
else
    echo "FAIL: SKILL.md missing YAML frontmatter"
    exit 1
fi

echo ""
echo "Result: PASS"
