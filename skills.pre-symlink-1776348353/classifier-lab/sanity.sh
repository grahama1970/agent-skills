#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [classifier-lab] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh scripts/benchmark.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL - missing $f"
        exit 1
    fi
done
echo "OK"

# Check 2: uv available
echo -n "Check 2: uv available... "
if ! command -v uv &>/dev/null; then
    echo "FAIL - uv not found"
    exit 1
fi
echo "OK"

# Determine python command: use skill venv if available, else system python
PYTHON="python3"
if [[ -f "$SCRIPT_DIR/.venv/bin/python" ]]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
fi

# Check 3: Core Python imports (torch, timm, torchvision, PIL)
echo -n "Check 3: Python imports (torch, timm, PIL, loguru)... "
if $PYTHON -c "
import torch
import timm
from PIL import Image
from loguru import logger
print(f'torch={torch.__version__}, timm={timm.__version__}', end='')
" 2>/dev/null; then
    echo " OK"
else
    # Try importing basic deps without ML
    if python3 -c "import torch" 2>/dev/null; then
        echo "WARN - torch found but timm/loguru missing (run ./run.sh once to bootstrap venv)"
    else
        echo "SKIP - torch/timm not in base Python (run ./run.sh once to bootstrap venv)"
    fi
fi

# Check 4: run.sh help works
echo -n "Check 4: run.sh help text... "
output=$("$SCRIPT_DIR/run.sh" 2>&1 || true)
if echo "$output" | grep -qi "classifier lab"; then
    echo "OK"
else
    echo "FAIL - run.sh did not produce expected help output"
    exit 1
fi

# Check 5: timm can list models (if available)
echo -n "Check 5: timm model listing... "
if $PYTHON -c "
import timm
models = timm.list_models('efficientnet_b0*')
assert len(models) > 0, 'No models found'
print(f'{len(models)} models', end='')
" 2>/dev/null; then
    echo " OK"
else
    echo "SKIP - timm not available"
fi

# Check 6: benchmark.py syntax
echo -n "Check 6: benchmark.py syntax... "
if ! python3 -c "import py_compile; py_compile.compile('$SCRIPT_DIR/scripts/benchmark.py', doraise=True)" 2>/dev/null; then
    echo "FAIL - syntax error"
    exit 1
fi
echo "OK"

echo "Result: PASS"
