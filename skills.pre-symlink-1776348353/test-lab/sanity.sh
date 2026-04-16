#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== test-lab sanity ==="

# Structure checks
check "SKILL.md exists" test -f "$SKILL_DIR/SKILL.md"
check "run.sh exists" test -f "$SKILL_DIR/run.sh"
check "run.sh is executable" test -x "$SKILL_DIR/run.sh"
check "pyproject.toml exists" test -f "$SKILL_DIR/pyproject.toml"
check "test_lab.py exists" test -f "$SKILL_DIR/test_lab.py"
check "generators/ exists" test -d "$SKILL_DIR/generators"
check "generators/python_tests.py exists" test -f "$SKILL_DIR/generators/python_tests.py"
check "generators/react_tests.py exists" test -f "$SKILL_DIR/generators/react_tests.py"
check "generators/kde_tests.py exists" test -f "$SKILL_DIR/generators/kde_tests.py"
check "generators/skill_tests.py exists" test -f "$SKILL_DIR/generators/skill_tests.py"

# Import check
check "test_lab imports cleanly" "$SKILL_DIR/.venv/bin/python" -c "import test_lab"

# Run against a known-bad snippet in isolated dir
BAD_DIR=$(mktemp -d /tmp/test_lab_sanity_XXXXXX)
cat > "$BAD_DIR/bad_code.py" <<'PYEOF'
import logging
import requests

def main():
    print("hello")
    try:
        pass
    except:
        pass
PYEOF

RESULT=$("$SKILL_DIR/.venv/bin/python" -m test_lab run "$BAD_DIR" --domain python --json 2>/dev/null || true)
rm -rf "$BAD_DIR"

if echo "$RESULT" | grep -q '"status": "FAIL"'; then
    echo "  PASS: Detects violations in bad Python file"
    PASS=$((PASS + 1))
else
    echo "  FAIL: Did not detect violations in bad Python file"
    FAIL=$((FAIL + 1))
fi

# Guard extension exists
GUARD="$SKILL_DIR/../../extensions/test-lab-guard.ts"
check "test-lab-guard.ts extension exists" test -f "$GUARD"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
