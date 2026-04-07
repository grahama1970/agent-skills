#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [create-lut] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh main.py pyproject.toml; do
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

# Check 3: Python imports (colour-science, numpy, cv2, click, rich)
echo -n "Check 3: Python imports... "
cd "$SCRIPT_DIR"
if ! uv run --project "$SCRIPT_DIR" python -c "
import numpy as np
import colour
import click
from rich.console import Console
print(f'numpy={np.__version__}, colour-science OK', end='')
" 2>/dev/null; then
    echo "FAIL - missing dependencies (colour-science, numpy, click, rich)"
    exit 1
fi
echo " OK"

# Check 4: main.py syntax
echo -n "Check 4: main.py syntax... "
if ! python3 -c "import py_compile; py_compile.compile('$SCRIPT_DIR/main.py', doraise=True)" 2>/dev/null; then
    echo "FAIL - syntax error"
    exit 1
fi
echo "OK"

# Check 5: Smoke test - generate identity LUT
echo -n "Check 5: Identity LUT generation smoke test... "
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

cd "$SCRIPT_DIR"
uv run --project "$SCRIPT_DIR" python main.py generate identity --size 5 -o "$TMPDIR/identity.cube" 2>/dev/null
if [[ -f "$TMPDIR/identity.cube" ]]; then
    # Verify it has LUT_3D_SIZE header
    if grep -q "LUT_3D_SIZE" "$TMPDIR/identity.cube"; then
        echo "OK"
    else
        echo "FAIL - generated file missing LUT_3D_SIZE header"
        exit 1
    fi
else
    echo "FAIL - identity.cube not generated"
    exit 1
fi

echo "Result: PASS"
