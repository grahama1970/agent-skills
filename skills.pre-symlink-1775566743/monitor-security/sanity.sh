#!/usr/bin/env bash
# Sanity check for monitor-security
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== monitor-security sanity check ==="

# 1. Check run.sh exists and is executable
echo "1/6 Checking run.sh..."
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not found or not executable"
    exit 1
fi

# 2. Check help output
echo "2/6 Checking help output..."
"$SCRIPT_DIR/run.sh" help > /dev/null || { echo "FAIL: help command failed"; exit 1; }

# 3. Check Python modules exist
echo "3/6 Checking Python modules..."
for module in monitor.py config.py reporter.py; do
    if [[ ! -f "$SCRIPT_DIR/$module" ]]; then
        echo "FAIL: $module not found"
        exit 1
    fi
done

# 4. Check probe directories exist
echo "4/6 Checking probe directories..."
if [[ ! -d "$SCRIPT_DIR/probes" ]]; then
    echo "FAIL: probes/ directory not found"
    exit 1
fi

# 5. Check Python imports
echo "5/6 Checking Python dependencies..."
uv run --directory "$SCRIPT_DIR" python -c "
from loguru import logger
import typer
print('Core dependencies OK')
" || { echo "FAIL: Python dependency check failed"; exit 1; }

# 6. Check state directory can be created
echo "6/6 Checking state directory..."
STATE_DIR="${MONITOR_STATE_DIR:-${HOME}/.pi/monitor-security}"
mkdir -p "$STATE_DIR" || { echo "FAIL: Cannot create state dir $STATE_DIR"; exit 1; }

echo "monitor-security sanity check PASSED"
