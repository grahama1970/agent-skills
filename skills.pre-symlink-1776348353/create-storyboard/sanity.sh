#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [create-storyboard] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh orchestrator.py screenplay_parser.py camera_planner.py panel_generator.py; do
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

# Check 3: FFmpeg available (for video assembly)
echo -n "Check 3: ffmpeg available... "
if command -v ffmpeg &>/dev/null; then
    echo "OK ($(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f3))"
else
    echo "SKIP - ffmpeg not found (needed for mp4 output)"
fi

# Check 4: Python imports (typer, PIL)
echo -n "Check 4: Python imports (typer, PIL)... "
if ! python3 -c "
import typer
from PIL import Image, ImageDraw
print('OK', end='')
" 2>/dev/null; then
    echo "FAIL - missing typer or Pillow"
    exit 1
fi
echo ""

# Check 5: Python syntax check on all modules
echo -n "Check 5: Python syntax check... "
fail_count=0
for f in "$SCRIPT_DIR"/*.py; do
    [[ ! -f "$f" ]] && continue
    if ! python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
        echo ""
        echo "  FAIL: syntax error in $(basename "$f")"
        ((fail_count++)) || true
    fi
done
if [[ $fail_count -gt 0 ]]; then
    exit 1
fi
echo "OK"

# Check 6: shot_taxonomy module loads
echo -n "Check 6: Shot taxonomy import... "
cd "$SCRIPT_DIR"
if ! python3 -c "
import sys; sys.path.insert(0, '.')
from shot_taxonomy import *
print('OK', end='')
" 2>/dev/null; then
    echo "FAIL - shot_taxonomy import failed"
    exit 1
fi
echo ""

echo "Result: PASS"
