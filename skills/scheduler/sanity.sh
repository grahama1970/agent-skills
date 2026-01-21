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

# 4. Check scheduler.py exists
if [[ ! -f "$SCRIPT_DIR/scheduler.py" ]]; then
    echo "  [FAIL] scheduler.py not found"
    exit 1
fi
echo "  [PASS] scheduler.py exists"

# 5. Test imports (install deps if needed)
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

# 6. Test rich import
if uv run --project "$SCRIPT_DIR" python -c "from rich.console import Console; print('ok')" 2>/dev/null | grep -q "ok"; then
    echo "  [PASS] Rich importable"
else
    echo "  [WARN] Rich not available (TUI disabled)"
fi

# 7. Test CLI help
if "$SCRIPT_DIR/run.sh" --help 2>&1 | grep -q "Background task scheduler"; then
    echo "  [PASS] CLI help works"
else
    echo "  [FAIL] CLI help failed"
    exit 1
fi

# 8. Test status command
if "$SCRIPT_DIR/run.sh" status --json 2>&1 | grep -q "running"; then
    echo "  [PASS] Status command works"
else
    echo "  [FAIL] Status command failed"
    exit 1
fi

# 9. Test list command
if "$SCRIPT_DIR/run.sh" list --json 2>&1; then
    echo "  [PASS] List command works"
else
    echo "  [FAIL] List command failed"
    exit 1
fi

echo "Result: PASS"
