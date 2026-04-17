#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

check() {
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS  $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== monitor-taxonomy sanity ==="

# 1. All Python files compile
for f in "$SCRIPT_DIR"/*.py "$SCRIPT_DIR"/probes/*.py; do
    check "py_compile $(basename "$f")" python -m py_compile "$f"
done

# 2. run.sh help works
check "run.sh help" "$SCRIPT_DIR/run.sh" help

# 3. SKILL.md exists and has triggers
check "SKILL.md exists" test -f "$SCRIPT_DIR/SKILL.md"
check "SKILL.md has triggers" grep -q "triggers:" "$SCRIPT_DIR/SKILL.md"

# 4. pyproject.toml exists
check "pyproject.toml exists" test -f "$SCRIPT_DIR/pyproject.toml"

# 5. Task spec exists
check "taxonomy-assessor.yaml exists" test -f "$SCRIPT_DIR/data/tasks/taxonomy-assessor.yaml"

# 6. Imports work (cascade, config)
check "import config" python -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); import config"
check "import probes" python -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); from probes import ProbeStatus, ProbeResult"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
