#!/usr/bin/env bash
# Real non-mocked sanity tests for monitor-workstation.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

PASS=0
FAIL=0
SKIP=0

check() {
    local label="$1"
    shift
    echo -n "  Check: $label ... "
    if "$@" > /dev/null 2>&1; then
        echo "OK"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
    fi
}

skip() {
    local label="$1"
    local count="${2:-1}"
    echo "  Skip: $label ($count checks)"
    SKIP=$((SKIP + count))
}

warn_check() {
    local label="$1"
    shift
    echo -n "  Warn: $label ... "
    if "$@" > /dev/null 2>&1; then
        echo "OK"
        PASS=$((PASS + 1))
    else
        echo "WARN (non-critical)"
        SKIP=$((SKIP + 1))
    fi
}

echo "=== monitor-workstation Sanity Check ==="
echo ""

# === Structure ===
echo "--- Structure ---"
check "SKILL.md exists" test -f "$SCRIPT_DIR/SKILL.md"
check "run.sh executable" test -x "$SCRIPT_DIR/run.sh"
check "monitor.py exists" test -f "$SCRIPT_DIR/monitor.py"
check "pyproject.toml exists" test -f "$SCRIPT_DIR/pyproject.toml"

# === Dependencies ===
echo ""
echo "--- Dependencies ---"
check "typer importable" uv run --directory "$SCRIPT_DIR" python -c "import typer"
check "rich importable" uv run --directory "$SCRIPT_DIR" python -c "import rich"
check "loguru importable" uv run --directory "$SCRIPT_DIR" python -c "from loguru import logger"
check "httpx importable" uv run --directory "$SCRIPT_DIR" python -c "import httpx"

# === CLI ===
echo ""
echo "--- CLI ---"
check "help works" "$SCRIPT_DIR/run.sh" help
check "monitor.py --help works" uv run --directory "$SCRIPT_DIR" python monitor.py --help

# === Real probe execution ===
echo ""
echo "--- Probes ---"
check "check command runs" "$SCRIPT_DIR/run.sh" check
check "check --json produces JSON" bash -c "$SCRIPT_DIR/run.sh check --json 2>/dev/null | python3 -c 'import sys,json; json.load(sys.stdin)'"

# === State directories ===
echo ""
echo "--- State ---"
check "state dir writable" bash -c "mkdir -p ~/.pi/monitor-workstation && test -w ~/.pi/monitor-workstation"

# === Cross-skill dependencies ===
echo ""
echo "--- Cross-skill Dependencies ---"
check "ops-workstation available" test -f "$PROJECT_ROOT/.pi/skills/ops-workstation/run.sh"
warn_check "ops-docker available" test -f "$PROJECT_ROOT/.pi/skills/ops-docker/run.sh"
warn_check "monitor-claude available" test -f "$PROJECT_ROOT/.pi/skills/monitor-claude/run.sh"
warn_check "scheduler available" test -f "$PROJECT_ROOT/.pi/skills/scheduler/run.sh"
warn_check "discord_notify importable" uv run --directory "$SCRIPT_DIR" python -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT/.pi/skills')
from common.discord_notify import notify_health
"
warn_check "12TB mounted" test -d /mnt/storage12tb

# === Summary ===
echo ""
echo "================================="
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
echo "================================="
[[ $FAIL -eq 0 ]]
