#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [surf-qml] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1 - Required files: "
FAIL=0
for f in SKILL.md run.sh surf_qml.py scenario_runner.py narration.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        FAIL=1
    fi
done
if [[ ! -d "$SCRIPT_DIR/scenarios" ]]; then
    echo "FAIL: missing scenarios/ directory"
    FAIL=1
fi
[[ $FAIL -eq 0 ]] && echo "PASS"
[[ $FAIL -ne 0 ]] && exit 1

# Check 2: Python syntax check on all .py files
echo -n "Check 2 - Python syntax: "
PY_FAIL=0
for py in "$SCRIPT_DIR"/*.py; do
    if [[ -f "$py" ]]; then
        if ! python3 -m py_compile "$py" 2>/dev/null; then
            echo "FAIL: syntax error in $(basename "$py")"
            PY_FAIL=1
        fi
    fi
done
[[ $PY_FAIL -eq 0 ]] && echo "PASS"
[[ $PY_FAIL -ne 0 ]] && exit 1

# Check 3: Core stdlib imports
echo -n "Check 3 - Core imports: "
python3 -c "
import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
print('PASS')
" || { echo "FAIL"; exit 1; }

# Check 4: AT-SPI availability (system package, not pip)
echo -n "Check 4 - AT-SPI (gi/Atspi): "
if python3 -c "import gi; gi.require_version('Atspi', '2.0'); from gi.repository import Atspi" 2>/dev/null; then
    echo "PASS"
else
    echo "WARN: pyatspi/gi not available"
    echo "  Install: sudo apt install python3-gi gir1.2-atspi-2.0 at-spi2-core"
    echo "  (surf-qml requires AT-SPI for Qt automation)"
fi

# Check 5: External tool dependencies
echo -n "Check 5 - External tools: "
TOOL_WARN=0
if ! command -v xdotool &>/dev/null; then
    echo ""
    echo "  WARN: xdotool not found (needed for keyboard/mouse)"
    TOOL_WARN=1
fi
if ! command -v ffmpeg &>/dev/null; then
    echo "  WARN: ffmpeg not found (needed for video recording)"
    TOOL_WARN=1
fi
if ! command -v import &>/dev/null; then
    echo "  WARN: ImageMagick import not found (needed for screenshots)"
    TOOL_WARN=1
fi
[[ $TOOL_WARN -eq 0 ]] && echo "PASS"

# Check 6: PyYAML (optional, for YAML scenarios)
echo -n "Check 6 - PyYAML: "
if python3 -c "import yaml" 2>/dev/null; then
    echo "PASS"
else
    echo "WARN: PyYAML not installed (YAML scenarios won't work, JSON still works)"
fi

# Check 7: Scenario files exist
echo -n "Check 7 - Scenario files: "
SCENARIO_COUNT=$(find "$SCRIPT_DIR/scenarios" -name '*.yaml' -o -name '*.json' 2>/dev/null | wc -l)
if [[ "$SCENARIO_COUNT" -gt 0 ]]; then
    echo "PASS ($SCENARIO_COUNT scenarios)"
else
    echo "WARN: no scenario files found"
fi

# Check 8: run.sh bash syntax
echo -n "Check 8 - run.sh bash syntax: "
if bash -n "$SCRIPT_DIR/run.sh" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL: run.sh has syntax errors"
    exit 1
fi

# Check 9: YAML frontmatter
echo -n "Check 9 - SKILL.md frontmatter: "
if head -1 "$SCRIPT_DIR/SKILL.md" | grep -q '^---'; then
    echo "PASS"
else
    echo "FAIL: SKILL.md missing YAML frontmatter"
    exit 1
fi

echo ""
echo "SKIP: AT-SPI desktop interaction (requires running desktop + Qt apps)"
echo "SKIP: Screenshot/recording tests (requires X11 display)"
echo "SKIP: Narration tests (requires PersonaPlex/Qwen3-TTS)"
echo ""
echo "Result: PASS"
