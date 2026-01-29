#!/bin/bash
set -eo pipefail

echo "=== scheduler Sanity Check ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Check Python available
if ! command -v python3 &>/dev/null; then
    echo "  [FAIL] Python3 not installed"
    exit 1
fi
echo "  [PASS] Python3 available"

# 2. Check uv available
if ! command -v uv &>/dev/null; then
    echo "  [FAIL] uv not installed"
    exit 1
fi
echo "  [PASS] uv available"

# 3. Check run.sh exists and is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [FAIL] run.sh not executable"
    exit 1
fi
echo "  [PASS] run.sh executable"

# 4. Check all required module files exist
REQUIRED_MODULES=(
    "scheduler.py"
    "config.py"
    "utils.py"
    "cron_parser.py"
    "job_registry.py"
    "executor.py"
    "metrics_server.py"
    "daemon.py"
    "commands.py"
    "report.py"
)

for module in "${REQUIRED_MODULES[@]}"; do
    if [[ ! -f "$SCRIPT_DIR/$module" ]]; then
        echo "  [FAIL] $module not found"
        exit 1
    fi
done
echo "  [PASS] All module files exist (${#REQUIRED_MODULES[@]} modules)"

# 5. Check module line counts (should be < 500 lines each)
MAX_LINES=500
for module in "${REQUIRED_MODULES[@]}"; do
    lines=$(wc -l < "$SCRIPT_DIR/$module")
    if [[ $lines -gt $MAX_LINES ]]; then
        echo "  [FAIL] $module exceeds $MAX_LINES lines ($lines lines)"
        exit 1
    fi
done
echo "  [PASS] All modules under $MAX_LINES lines"

# 6. Test imports (install deps if needed)
if ! uv run --project "$SCRIPT_DIR" python -c "from apscheduler.schedulers.background import BackgroundScheduler" 2>/dev/null; then
    echo "  [WARN] Installing dependencies..."
    uv sync --project "$SCRIPT_DIR" 2>/dev/null || true
fi

if uv run --project "$SCRIPT_DIR" python -c "from apscheduler.schedulers.background import BackgroundScheduler; print('ok')" 2>/dev/null | grep -q "ok"; then
    echo "  [PASS] APScheduler importable"
else
    echo "  [FAIL] APScheduler not importable"
    exit 1
fi

# 7. Test rich import
if uv run --project "$SCRIPT_DIR" python -c "from rich.console import Console; print('ok')" 2>/dev/null | grep -q "ok"; then
    echo "  [PASS] Rich importable"
else
    echo "  [WARN] Rich not available (TUI disabled)"
fi

# 8. Test modular imports (check for circular import issues)
cd "$SCRIPT_DIR"
if uv run --project "$SCRIPT_DIR" python -c "
import sys
sys.path.insert(0, '.')
from config import DATA_DIR, JOBS_FILE
from utils import rprint, ensure_dirs
from cron_parser import parse_interval
from job_registry import load_jobs, save_jobs
from executor import run_job
from daemon import SchedulerDaemon
from commands import cmd_status
from report import generate_report_data
print('ok')
" 2>/dev/null | grep -q "ok"; then
    echo "  [PASS] Module imports work (no circular imports)"
else
    echo "  [FAIL] Module imports failed (possible circular import)"
    exit 1
fi

# 9. Test CLI help
if "$SCRIPT_DIR/run.sh" --help 2>&1 | grep -q "Background task scheduler"; then
    echo "  [PASS] CLI help works"
else
    echo "  [FAIL] CLI help failed"
    exit 1
fi

# 10. Test status command
if "$SCRIPT_DIR/run.sh" status --json 2>&1 | grep -q "running"; then
    echo "  [PASS] Status command works"
else
    echo "  [FAIL] Status command failed"
    exit 1
fi

# 11. Test list command
if "$SCRIPT_DIR/run.sh" list --json 2>&1; then
    echo "  [PASS] List command works"
else
    echo "  [FAIL] List command failed"
    exit 1
fi

# 12. Check monolith backup exists
if [[ -f "$SCRIPT_DIR/scheduler_monolith.py" ]]; then
    echo "  [PASS] Original monolith preserved (scheduler_monolith.py)"
else
    echo "  [WARN] No monolith backup found"
fi

echo ""
echo "=== Module Summary ==="
for module in "${REQUIRED_MODULES[@]}"; do
    lines=$(wc -l < "$SCRIPT_DIR/$module")
    printf "  %-25s %4d lines\n" "$module" "$lines"
done
if [[ -f "$SCRIPT_DIR/scheduler_monolith.py" ]]; then
    lines=$(wc -l < "$SCRIPT_DIR/scheduler_monolith.py")
    printf "  %-25s %4d lines (original)\n" "scheduler_monolith.py" "$lines"
fi

echo ""
echo "Result: PASS"
