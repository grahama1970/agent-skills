#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SKILL_DIR}/src:${SKILL_DIR}/../../skills:${PYTHONPATH:-}"

PASS=0
FAIL=0

check() {
    local name="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  ✓ $name"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $name"
        FAIL=$((FAIL + 1))
    fi
}

echo "recommend-skill-chain sanity checks"
echo "===================================="

# 1. Python imports
check "Python imports (recommender)" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}/src')
from src.recommender import recommend, evaluate, get_status
"

# 2. Skill-lab availability
check "skill-lab scripts exist" test -d "${SKILL_DIR}/../skill-lab/scripts"

# 3. Assistant availability
check "assistant module exists" test -f "${SKILL_DIR}/../assistant/assistant.py"

# 4. Health check via status
check "status command runs" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}/src')
from src.recommender import get_status
s = get_status()
assert isinstance(s, dict), 'status must return dict'
assert 'components' in s, 'status must have components'
"

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
