#!/usr/bin/env bash
# Sanity check for assistant-lab
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_DIR="${SCRIPT_DIR}/../common"
ASSISTANT_DIR="${SCRIPT_DIR}/../assistant"

echo "=== assistant-lab sanity check ==="

# 1. Check help output
echo "1/5 Checking help output..."
"$SCRIPT_DIR/run.sh" help > /dev/null || { echo "FAIL: help command failed"; exit 1; }

# 2. Check model_factory imports
echo "2/5 Checking model_factory imports..."
python3 -c "
import sys
sys.path.insert(0, '${COMMON_DIR}')
from model_factory import ModelFactory, TrainResult, EvalResult
" || { echo "FAIL: model_factory import failed"; exit 1; }

# 3. Check composed skills exist
echo "3/5 Checking composed skills exist..."
for skill in create-gpt create-classifier ops-runpod; do
    if [[ ! -d "${SCRIPT_DIR}/../${skill}" ]]; then
        echo "WARNING: /${skill} not found at ${SCRIPT_DIR}/../${skill}"
    fi
done

# 4. Check metrics dir can be created
echo "4/5 Checking metrics directory..."
METRICS_DIR="${ASSISTANT_METRICS_DIR:-${HOME}/.pi/assistant}"
mkdir -p "${METRICS_DIR}" || { echo "FAIL: Cannot create metrics dir"; exit 1; }

# 5. Test status command (non-destructive)
echo "5/5 Testing status command..."
"$SCRIPT_DIR/run.sh" status > /dev/null 2>&1 || { echo "FAIL: status command failed"; exit 1; }

echo "assistant-lab sanity check PASSED"
