#!/usr/bin/env bash
# Sanity check for classifier-lab-subagent
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$SCRIPT_DIR")"
ERRORS=0

echo "=== classifier-lab-subagent sanity check ==="

# 1. Check orchestrator.py exists and imports
if [ ! -f "$SCRIPT_DIR/orchestrator.py" ]; then
    echo "FAIL: orchestrator.py not found"
    ERRORS=$((ERRORS + 1))
else
    echo "PASS: orchestrator.py exists"
fi

# 2. Check classifier-lab dependency
if [ ! -f "$SKILLS_DIR/classifier-lab/run.sh" ]; then
    echo "FAIL: classifier-lab/run.sh not found"
    ERRORS=$((ERRORS + 1))
else
    echo "PASS: classifier-lab available"
fi

# 3. Check scillm reachable (warn, not fail — replaced subagent-service)
if curl -s --max-time 3 http://localhost:4001/health > /dev/null 2>&1; then
    echo "PASS: scillm reachable"
else
    echo "WARN: scillm not reachable (will use heuristic HP fallback)"
fi

# 4. Check Python imports
cd "$SCRIPT_DIR"
unset VIRTUAL_ENV
uv run --project "$SCRIPT_DIR" python -c "
import httpx
import typer
from loguru import logger
print('PASS: Python imports OK')
" 2>/dev/null || { echo "FAIL: Python imports"; ERRORS=$((ERRORS + 1)); }

# 5. Check scillm reachable (warn, not fail)
if curl -s --max-time 3 http://localhost:4001/health > /dev/null 2>&1; then
    echo "PASS: scillm reachable"
else
    echo "WARN: scillm not reachable (will use heuristic HP fallback)"
fi

# 6. Check HuggingFace datasets available
uv run --project "$SCRIPT_DIR" python -c "
import datasets
print('PASS: datasets package available')
" 2>/dev/null || { echo "FAIL: datasets package"; ERRORS=$((ERRORS + 1)); }

echo ""
if [ $ERRORS -eq 0 ]; then
    echo "=== ALL CHECKS PASSED ==="
    exit 0
else
    echo "=== $ERRORS CHECKS FAILED ==="
    exit 1
fi
