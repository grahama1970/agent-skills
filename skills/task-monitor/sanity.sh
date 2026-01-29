#!/usr/bin/env bash
# Sanity check for task-monitor skill (modular version)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Sanity check for task-monitor (modular) ==="

# Check python3 exists
if ! command -v python3 >/dev/null 2>&1; then
    echo "FAIL: python3 not found"
    exit 1
fi
echo "PASS: python3 found"

# Check main entry point exists
if [[ ! -f "$SCRIPT_DIR/monitor.py" ]]; then
    echo "FAIL: monitor.py not found"
    exit 1
fi
echo "PASS: monitor.py exists"

# Check monolith backup exists
if [[ ! -f "$SCRIPT_DIR/monitor_monolith.py" ]]; then
    echo "WARN: monitor_monolith.py backup not found"
else
    echo "PASS: monitor_monolith.py backup exists"
fi

# Check package structure
MODULES=(
    "task_monitor/__init__.py"
    "task_monitor/config.py"
    "task_monitor/models.py"
    "task_monitor/stores.py"
    "task_monitor/utils.py"
    "task_monitor/tui.py"
    "task_monitor/http_api.py"
    "task_monitor/cli.py"
)

for module in "${MODULES[@]}"; do
    if [[ ! -f "$SCRIPT_DIR/$module" ]]; then
        echo "FAIL: $module not found"
        exit 1
    fi
done
echo "PASS: All modules exist (${#MODULES[@]} files)"

# Check module line counts (should be < 500 lines)
MAX_LINES=500
for module in "${MODULES[@]}"; do
    lines=$(wc -l < "$SCRIPT_DIR/$module")
    if [[ $lines -gt $MAX_LINES ]]; then
        echo "FAIL: $module has $lines lines (max $MAX_LINES)"
        exit 1
    fi
done
echo "PASS: All modules < $MAX_LINES lines"

# Check SKILL.md exists
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi
echo "PASS: SKILL.md exists"

# Check import chain works
echo "Checking imports..."
if uv run python3 -c "from task_monitor import TaskConfig, TaskRegistry, HistoryStore" 2>&1; then
    echo "PASS: Basic imports work"
else
    echo "FAIL: Import check failed"
    exit 1
fi

# Check CLI help works
echo "Checking CLI..."
if uv run python3 "$SCRIPT_DIR/monitor.py" --help >/dev/null 2>&1; then
    echo "PASS: CLI --help works"
else
    echo "FAIL: CLI --help failed"
    exit 1
fi

# Check for circular imports by importing all modules
echo "Checking for circular imports..."
if uv run python3 -c "
from task_monitor import config
from task_monitor import models
from task_monitor import stores
from task_monitor import utils
from task_monitor import tui
from task_monitor import http_api
from task_monitor import cli
print('All modules imported successfully')
" 2>&1; then
    echo "PASS: No circular imports detected"
else
    echo "FAIL: Circular import detected"
    exit 1
fi

# Check status command works (basic functionality test)
echo "Checking status command..."
if uv run python3 "$SCRIPT_DIR/monitor.py" status 2>&1; then
    echo "PASS: status command works"
else
    echo "WARN: status command returned non-zero (may be expected if no tasks)"
fi

echo ""
echo "=== Module Line Counts ==="
for module in "${MODULES[@]}"; do
    lines=$(wc -l < "$SCRIPT_DIR/$module")
    printf "  %-30s %4d lines\n" "$module" "$lines"
done

echo ""
echo "=== Sanity check complete ==="
