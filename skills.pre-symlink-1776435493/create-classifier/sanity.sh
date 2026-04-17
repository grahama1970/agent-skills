#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [create-classifier] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh scripts/collect_labels.py scripts/evaluate.py scripts/assess_task.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL - missing $f"
        exit 1
    fi
done
echo "OK"

# Determine python command: use skill venv if available, else system python
PYTHON="python3"
if [[ -f "$SCRIPT_DIR/.venv/bin/python" ]]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
fi

# Check 2: Python syntax check on all scripts
echo -n "Check 2: Python syntax check... "
fail_count=0
for f in "$SCRIPT_DIR"/scripts/*.py "$SCRIPT_DIR"/templates/*.py; do
    [[ ! -f "$f" ]] && continue
    if ! python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
        echo "FAIL - syntax error in $(basename "$f")"
        ((fail_count++)) || true
    fi
done
if [[ $fail_count -gt 0 ]]; then
    exit 1
fi
echo "OK"

# Check 3: Core Python imports (torch, timm)
echo -n "Check 3: Core Python imports (torch, timm, PIL)... "
if $PYTHON -c "
import torch
import timm
from PIL import Image
from loguru import logger
print(f'torch={torch.__version__}', end='')
" 2>/dev/null; then
    echo " OK"
else
    echo "SKIP - torch/timm not available (run ./run.sh once to bootstrap venv)"
fi

# Check 4: CLI help works
echo -n "Check 4: run.sh help... "
output=$("$SCRIPT_DIR/run.sh" help 2>&1 || true)
if echo "$output" | grep -qi "create-classifier\|classifier"; then
    echo "OK"
else
    echo "FAIL - run.sh did not produce expected help"
    exit 1
fi

# Check 5: timm model creation (smoke test, if available)
echo -n "Check 5: timm model creation smoke test... "
if $PYTHON -c "
import timm
model = timm.create_model('efficientnet_b0', pretrained=False, num_classes=4)
print(f'params={sum(p.numel() for p in model.parameters())}', end='')
" 2>/dev/null; then
    echo " OK"
else
    echo "SKIP - timm not available"
fi

echo "Result: PASS"
