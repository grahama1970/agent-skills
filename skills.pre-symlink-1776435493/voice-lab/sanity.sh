#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [voice-lab] Sanity Check ==="

# Use uv run if pyproject.toml exists (ensures correct venv)
if [[ -f "$SCRIPT_DIR/pyproject.toml" ]] && command -v uv &>/dev/null; then
    PY="uv run --directory $SCRIPT_DIR python"
else
    PY="python3"
fi

# Check 1: Required files exist
echo -n "Check 1 - Required files: "
FAIL=0
for f in SKILL.md voice_lab.py waveform.py quality.py devices.py capture.py alignment.py session.py lesson.py quality_gate.py sweep.py evaluate.py presets.py; do
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
        if ! $PY -m py_compile "$py" 2>/dev/null; then
            echo "FAIL: syntax error in $(basename "$py")"
            PY_FAIL=1
        fi
    fi
done
[[ $PY_FAIL -eq 0 ]] && echo "PASS"
[[ $PY_FAIL -ne 0 ]] && exit 1

# Check 3: Core imports
echo -n "Check 3 - typer + rich + loguru: "
$PY -c "
import typer
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
print('PASS')
" || { echo "FAIL: typer/rich/loguru not installed"; exit 1; }

echo -n "Check 3b - numpy + soundfile: "
$PY -c "
import numpy
import soundfile
print('PASS')
" || { echo "FAIL: numpy/soundfile not installed"; exit 1; }

# Check 4: PipeWire tools
echo -n "Check 4 - PipeWire tools: "
PW_FAIL=0
for tool in pw-record pw-play pw-cli wpctl; do
    if ! command -v "$tool" &>/dev/null; then
        echo ""
        echo "  FAIL: $tool not found"
        PW_FAIL=1
    fi
done
[[ $PW_FAIL -eq 0 ]] && echo "PASS"
[[ $PW_FAIL -ne 0 ]] && exit 1

# Check 5: CLI loads with all commands
echo -n "Check 5 - CLI help: "
cd "$SCRIPT_DIR"
if $PY voice_lab.py --help >/dev/null 2>&1; then
    echo "PASS"
else
    echo "FAIL: CLI help failed"
    exit 1
fi

# Check 6: devices command smoke test
echo -n "Check 6 - devices command: "
if $PY voice_lab.py devices --json 2>/dev/null | $PY -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d,list)" 2>/dev/null; then
    echo "PASS"
else
    echo "WARN: devices command failed (PipeWire may not be running)"
fi

# Check 7: waveform module
echo -n "Check 7 - waveform module: "
$PY -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
import numpy as np
from waveform import compute_stats, resample_for_display, ascii_waveform, AudioStats
sr = 24000
t = np.linspace(0, 1.0, sr)
audio = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
stats = compute_stats(audio, sr)
assert isinstance(stats, AudioStats)
mins, maxs = resample_for_display(audio, 80)
assert len(mins) == 80
print('PASS')
" || { echo "FAIL"; exit 1; }

# Check 8: quality module
echo -n "Check 8 - quality module: "
$PY -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
import numpy as np
from quality import QualityMetrics, compute_naturalness, detect_artifacts
sr = 24000
t = np.linspace(0, 1.0, sr)
audio = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
nat = compute_naturalness(audio, sr)
assert 1.0 <= nat <= 5.0
art = detect_artifacts(audio, sr)
assert 0.0 <= art <= 1.0
print('PASS')
" || { echo "FAIL"; exit 1; }

# Check 9: alignment module (SRT parsing)
echo -n "Check 9 - alignment module: "
$PY -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from alignment import parse_srt, SRTSegment
from pathlib import Path
import tempfile, os
srt_content = '''1
00:00:01,000 --> 00:00:03,000
Hello world

2
00:00:04,000 --> 00:00:06,500
Testing alignment
'''
with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
    f.write(srt_content)
    f.flush()
    segs = parse_srt(Path(f.name))
    os.unlink(f.name)
assert len(segs) == 2
assert segs[0].text == 'Hello world'
assert segs[0].start_ms == 1000
assert segs[1].end_ms == 6500
print('PASS')
" || { echo "FAIL"; exit 1; }

# Check 10: Storage directory
echo -n "Check 10 - 12TB storage: "
if [[ -d "/mnt/storage12tb/media/personas" ]]; then
    echo "PASS"
else
    echo "WARN: /mnt/storage12tb/media/personas not mounted"
fi

# Check 11: AEC module
echo -n "Check 11 - AEC module: "
AEC_CONF="/etc/pipewire/pipewire.conf.d/99-openclaw-aec.conf"
if [[ -f "$AEC_CONF" ]]; then
    if grep -q "echo-cancel" "$AEC_CONF" 2>/dev/null; then
        echo "WARN: OpenClaw AEC active (may cause XRUNs on USB devices)"
    else
        echo "PASS (AEC config present but inactive)"
    fi
else
    echo "PASS (no AEC config)"
fi

# Check 12: Docker RVC container
echo -n "Check 12 - Docker RVC container: "
if command -v docker &>/dev/null; then
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "rvc-training"; then
        if docker exec rvc-training python -c "import torch; print('ok')" 2>/dev/null | grep -q "ok"; then
            echo "PASS (running + torch OK)"
        else
            echo "WARN: rvc-training running but torch import failed"
        fi
    else
        echo "WARN: rvc-training container not running"
    fi
else
    echo "WARN: docker not found"
fi

# Check 13: QML Editor (optional - PySide6)
echo -n "Check 13 - QML Editor: "
if $PY -c "from editor import launch_editor; from editor_bridge import VoiceLabBridge; from waveform_painter import WaveformPainter; print('ok')" 2>/dev/null | grep -q "ok"; then
    echo "PASS (PySide6 editor available)"
else
    echo "WARN: PySide6 not installed (editor disabled, CLI still works)"
fi

echo ""
echo "SKIP: Audio generation (requires GPU + Qwen3-TTS model)"
echo "SKIP: Speaker similarity (requires resemblyzer or librosa)"
echo ""
echo "Result: PASS"
