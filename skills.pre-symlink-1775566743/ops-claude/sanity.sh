#!/bin/bash
#
# Sanity check for ops-claude skill
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Ops-Claude Sanity Check ==="

PASS=0
FAIL=0

check() {
    local name="$1"
    local cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then
        echo "[OK] $name"
        PASS=$((PASS + 1))
    else
        echo "[FAIL] $name"
        FAIL=$((FAIL + 1))
    fi
}

# Check script exists and is executable
check "run.sh exists" "test -f run.sh"
check "run.sh is executable" "test -x run.sh"
check "SKILL.md exists" "test -f SKILL.md"
check "usage.py exists" "test -f usage.py"
check "nightly_usage.py exists" "test -f nightly_usage.py"
check "pyproject.toml exists" "test -f pyproject.toml"

# Check commands work
check "help command" "./run.sh --help"
check "status command" "./run.sh status"

# Check inotify access
check "can read inotify limits" "cat /proc/sys/fs/inotify/max_user_watches"

# Check find_skills_dirs functionality
check "can find skills dirs" "test -d $HOME/.claude/skills || test -d $HOME/.pi/skills"

# Check ccusage is available
check "ccusage installed" "command -v ccusage"

# Check usage analytics (basic smoke test)
check "report command" "./run.sh report --daily --days 1 --json"
check "savings command" "./run.sh savings --json"
check "top-projects command" "./run.sh top-projects --days 1 --json"

# Check scheduler job registered
check "nightly job registered" "python3 -c \"import json; j=json.load(open('$HOME/.pi/scheduler/jobs.json')); assert 'claude-usage-nightly' in j\""

echo ""
echo "============================================================"
echo "SANITY CHECK COMPLETE: $PASS passed, $FAIL failed"
echo "============================================================"

[[ $FAIL -eq 0 ]] && exit 0 || exit 1
