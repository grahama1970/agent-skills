#!/usr/bin/env bash
# Sanity check for /switchboard skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SWITCHBOARD_PKG="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")/packages/switchboard"
SWITCHBOARD_URL="${SWITCHBOARD_URL:-http://127.0.0.1:7890}"
ERRORS=0

echo "=== /switchboard sanity check ==="

# 1. Switchboard package exists
if [[ -f "$SWITCHBOARD_PKG/index.ts" ]]; then
    echo "PASS: packages/switchboard/index.ts exists"
else
    echo "FAIL: packages/switchboard/index.ts not found"
    ERRORS=$((ERRORS + 1))
fi

# 2. Executor module exists
if [[ -f "$SWITCHBOARD_PKG/src/executor.ts" ]]; then
    echo "PASS: executor.ts exists"
else
    echo "FAIL: executor.ts not found"
    ERRORS=$((ERRORS + 1))
fi

# 3. run.sh executable
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "PASS: run.sh executable"
else
    echo "FAIL: run.sh not executable"
    ERRORS=$((ERRORS + 1))
fi

# 4. Switchboard server reachable (warn, not fail)
if curl -s --max-time 3 "$SWITCHBOARD_URL/health" > /dev/null 2>&1; then
    echo "PASS: Switchboard server reachable"
else
    echo "WARN: Switchboard server not reachable (start with: ./run.sh server-start)"
fi

# 5. YAML parser available
if python3 -c "import yaml" 2>/dev/null; then
    echo "PASS: PyYAML available"
else
    echo "FAIL: PyYAML not installed (pip install pyyaml)"
    ERRORS=$((ERRORS + 1))
fi

echo ""
if [[ $ERRORS -eq 0 ]]; then
    echo "=== ALL CHECKS PASSED ==="
    exit 0
else
    echo "=== $ERRORS CHECKS FAILED ==="
    exit 1
fi
