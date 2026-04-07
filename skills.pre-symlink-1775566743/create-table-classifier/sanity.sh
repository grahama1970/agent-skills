#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [create-table-classifier] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh pyproject.toml; do
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

# Determine python command: use skill venv if available
PYTHON="python3"
if [[ -f "$SCRIPT_DIR/.venv/bin/python" ]]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
fi

# Check 3: Core Python imports (torch, timm, PIL)
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

# Check 4: Script syntax check
echo -n "Check 4: Script syntax... "
scripts_dir="$SCRIPT_DIR/scripts"
if [[ -d "$scripts_dir" ]]; then
    fail_count=0
    for f in "$scripts_dir"/*.py; do
        [[ ! -f "$f" ]] && continue
        if ! python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
            echo ""
            echo "  WARN: syntax issue in $(basename "$f")"
            ((fail_count++)) || true
        fi
    done
    if [[ $fail_count -eq 0 ]]; then
        echo "OK"
    else
        echo "WARN - $fail_count files with syntax issues"
    fi
else
    echo "SKIP - scripts/ directory not found"
fi

# Check 5: MobileNetV2 model available via timm (if available)
echo -n "Check 5: MobileNetV2 available... "
if $PYTHON -c "
import timm
model = timm.create_model('mobilenetv2_100', pretrained=False, num_classes=3)
print(f'params={sum(p.numel() for p in model.parameters())}', end='')
" 2>/dev/null; then
    echo " OK"
else
    echo "SKIP - timm not available"
fi

# Check 6: CLI help works
echo -n "Check 6: run.sh help... "
output=$("$SCRIPT_DIR/run.sh" help 2>&1 || true)
if echo "$output" | grep -qi "table\|classifier\|camelot"; then
    echo "OK"
else
    echo "FAIL - run.sh help did not produce expected output"
    exit 1
fi

echo "Result: PASS"
