#!/usr/bin/env bash
# Sanity check for monitor-claude skill.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ERRORS=0

echo "=== monitor-claude sanity ==="

# Check monitor.py exists
if [[ -f "$SCRIPT_DIR/monitor.py" ]]; then
    echo "[OK] monitor.py found"
else
    echo "[FAIL] monitor.py not found"
    ERRORS=$((ERRORS + 1))
fi

# Check pyproject.toml
if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    echo "[OK] pyproject.toml found"
else
    echo "[FAIL] pyproject.toml not found"
    ERRORS=$((ERRORS + 1))
fi

# Run status command (should always work — just reads ps output)
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/monitor.py" status 2>/dev/null; then
    echo "[OK] status command works"
else
    echo "[FAIL] status command failed"
    ERRORS=$((ERRORS + 1))
fi

if [[ $ERRORS -gt 0 ]]; then
    echo "SANITY FAILED: $ERRORS error(s)"
    exit 1
fi

echo "SANITY OK"
