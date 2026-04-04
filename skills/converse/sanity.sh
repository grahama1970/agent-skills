#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [converse] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1 - Required files: "
FAIL=0
for f in SKILL.md run.sh converse.py emotion.py listener.py thinker.py speaker.py mixer.py idler.py surfaces.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        FAIL=1
    fi
done
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
echo -n "Check 3 - Core stdlib imports: "
python3 -c "
import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
print('PASS')
" || { echo "FAIL"; exit 1; }

# Check 4: numpy + loguru (required deps)
echo -n "Check 4 - numpy: "
if python3 -c "import numpy" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL: numpy not installed"
    exit 1
fi

echo -n "Check 4b - loguru: "
if python3 -c "from loguru import logger" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL: loguru not installed"
    exit 1
fi

# Check 5: Optional deps (WARN, not FAIL)
echo -n "Check 5 - Optional deps: "
OPTIONAL_WARN=0
if ! python3 -c "import webrtcvad" 2>/dev/null; then
    echo ""
    echo "  WARN: webrtcvad not installed (will use energy-based VAD fallback)"
    OPTIONAL_WARN=1
fi
if ! python3 -c "import faster_whisper" 2>/dev/null; then
    echo "  WARN: faster-whisper not installed (will use CLI fallback)"
    OPTIONAL_WARN=1
fi
if ! python3 -c "import websockets" 2>/dev/null; then
    echo "  WARN: websockets not installed (needed for Horus surface only)"
    OPTIONAL_WARN=1
fi
[[ $OPTIONAL_WARN -eq 0 ]] && echo "PASS (all optional deps present)"

# Check 6: PipeWire tools (needed for KDE surface)
echo -n "Check 6 - PipeWire tools: "
if command -v pw-record &>/dev/null && command -v pw-play &>/dev/null; then
    echo "PASS"
else
    echo "WARN: pw-record/pw-play not found (needed for KDE surface)"
fi

# Check 7: Smoke test - import emotion module standalone
echo -n "Check 7 - Emotion module import: "
cd "$SCRIPT_DIR"
python3 -c "
import sys
sys.path.insert(0, '.')
from emotion import EmotionState, EmotionStateMachine
e = EmotionStateMachine()
assert hasattr(e, 'state'), 'EmotionStateMachine missing state'
print('PASS')
" || { echo "FAIL"; exit 1; }

# Check 8: Smoke test - mixer module
echo -n "Check 8 - Mixer module: "
cd "$SCRIPT_DIR"
python3 -c "
import sys, numpy as np
sys.path.insert(0, '.')
from mixer import AudioMixer
m = AudioMixer()
m.add_channel('test')
print('PASS')
" || { echo "FAIL"; exit 1; }

# SKIP: GPU, API keys, PersonaPlex, Whisper model, live audio
echo ""
echo "SKIP: GPU-dependent checks (PersonaPlex, Whisper, Qwen3-TTS)"
echo "SKIP: API key checks (Ollama, external LLMs)"
echo "SKIP: Live audio I/O (requires hardware)"

echo ""
echo "Result: PASS"
