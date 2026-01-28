#!/usr/bin/env bash
# Sanity check for task-monitor skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Sanity check for task-monitor ==="

# Check python3 exists
if ! command -v python3 >/dev/null 2>&1; then
    echo "FAIL: python3 not found"
    exit 1
fi
echo "PASS: python3 found"

# Check main script exists
if [[ ! -f "$SCRIPT_DIR/monitor.py" ]]; then
    echo "FAIL: monitor.py not found"
    exit 1
fi
echo "PASS: monitor.py exists"

# Check monitor_adapter.py exists
if [[ ! -f "$SCRIPT_DIR/monitor_adapter.py" ]]; then
    echo "WARN: monitor_adapter.py not found"
else
    echo "PASS: monitor_adapter.py exists"
fi

# Check SKILL.md exists
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi
echo "PASS: SKILL.md exists"

# Check CLI help works
if python3 "$SCRIPT_DIR/monitor.py" --help >/dev/null 2>&1; then
    echo "PASS: CLI --help works"
else
    echo "WARN: CLI --help check failed (may need dependencies)"
fi

# Check rich is available (used for TUI)
if python3 -c "import rich" 2>/dev/null; then
    echo "PASS: rich available"
else
    echo "WARN: rich not installed (pip install rich)"
fi

echo "=== Sanity check complete ==="
