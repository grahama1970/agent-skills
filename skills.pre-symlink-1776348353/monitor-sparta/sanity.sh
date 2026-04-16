#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORY_DIR="/home/graham/workspace/experiments/memory"
MONITOR_SCRIPT="$MEMORY_DIR/scripts/validation/monitor_sparta.py"

echo "monitor-sparta sanity check..."

# Check memory workspace exists
if [ ! -d "$MEMORY_DIR" ]; then
  echo "FAIL: memory workspace not found at $MEMORY_DIR"
  exit 1
fi

# Check monitor script exists
if [ ! -f "$MONITOR_SCRIPT" ]; then
  echo "FAIL: monitor_sparta.py not found at $MONITOR_SCRIPT"
  exit 1
fi

# Check memory venv exists
if [ ! -d "$MEMORY_DIR/.venv" ]; then
  echo "FAIL: memory .venv not found"
  exit 1
fi

# Activate venv and test help
source "$MEMORY_DIR/.venv/bin/activate"
cd "$MEMORY_DIR"

# Test that monitor script can show help
if ! python "$MONITOR_SCRIPT" --help >/dev/null 2>&1; then
  echo "FAIL: monitor_sparta.py --help failed"
  exit 1
fi

# Test status command (should work even with no running monitor)
if ! python "$MONITOR_SCRIPT" status >/dev/null 2>&1; then
  echo "FAIL: monitor_sparta.py status failed"
  exit 1
fi

echo "PASS: monitor-sparta sanity check"
exit 0
