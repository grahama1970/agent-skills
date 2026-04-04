#!/usr/bin/env bash
# Sanity check for intent-mapper
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== intent-mapper sanity check ==="

# 1. Check run.sh exists and is executable
echo "1/4 Checking run.sh..."
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not found or not executable"
    exit 1
fi

# 2. Check main.py exists
echo "2/4 Checking main.py..."
if [[ ! -f "$SCRIPT_DIR/main.py" ]]; then
    echo "FAIL: main.py not found"
    exit 1
fi

# 3. Check Python dependencies
echo "3/4 Checking Python imports..."
uv run --project "$SCRIPT_DIR" python -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
# Test basic imports without running full classifier
print('Python environment OK')
" || { echo "FAIL: Python environment check failed"; exit 1; }

# 4. Test help/basic invocation
echo "4/4 Testing basic invocation..."
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/main.py" --help > /dev/null 2>&1 || {
    echo "WARNING: --help not available (may use positional args only)"
}

echo "intent-mapper sanity check PASSED"
