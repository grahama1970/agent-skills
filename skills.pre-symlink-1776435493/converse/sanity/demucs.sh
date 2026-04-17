#!/usr/bin/env bash
# Sanity check: Demucs can separate stems from audio
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEMS_SKILL="/home/graham/workspace/experiments/pi-mono/.pi/skills/create-stems"

echo "=== Demucs Sanity Check ==="

# Check 1: create-stems skill exists
echo -n "  [1/4] create-stems skill: "
if [[ -d "$STEMS_SKILL" ]] && [[ -f "$STEMS_SKILL/run.sh" ]]; then
    echo "PASS"
else
    echo "FAIL: create-stems skill not found at $STEMS_SKILL"
    exit 1
fi

# Check 2: Demucs importable in create-stems venv
echo -n "  [2/4] Demucs import: "
cd "$STEMS_SKILL"
if [[ ! -d ".venv" ]]; then
    echo -n "(syncing venv...) "
    uv sync --quiet 2>/dev/null || true
fi
if uv run python -c "import demucs.separate; print('ok')" >/dev/null 2>&1; then
    echo "PASS"
else
    echo "FAIL: cannot import demucs.separate"
    exit 1
fi

# Check 3: GPU availability
echo -n "  [3/4] GPU (torch.cuda): "
CUDA=$(uv run python -c "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')" 2>/dev/null || echo "cpu")
if [[ "$CUDA" == "cuda" ]]; then
    GPU=$(uv run python -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null || echo "unknown")
    echo "PASS ($GPU)"
else
    echo "WARN: CPU only (will be slow)"
fi

# Check 4: Separate a short test WAV
echo -n "  [4/4] Stem separation test: "
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# Generate a 2-second test tone
uv run python -c "
import numpy as np, soundfile as sf
sr = 44100
t = np.linspace(0, 2, sr * 2)
# Simple mix: 440Hz sine + 220Hz sine (simulates vocals + bass)
audio = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 220 * t)
sf.write('${TMPDIR}/test_mix.wav', audio.astype(np.float32), sr)
" 2>/dev/null

if [[ ! -f "${TMPDIR}/test_mix.wav" ]]; then
    echo "FAIL: Could not generate test audio"
    exit 1
fi

# Run separation (htdemucs is faster than htdemucs_6s for sanity)
if uv run python -c "
import demucs.separate
import sys
sys.argv = ['demucs', '-n', 'htdemucs', '--two-stems', 'vocals', '-o', '${TMPDIR}/stems', '${TMPDIR}/test_mix.wav']
demucs.separate.main()
" >/dev/null 2>&1; then
    VOCALS=$(find "${TMPDIR}/stems" -name "vocals.wav" | head -1)
    if [[ -n "$VOCALS" ]] && [[ -f "$VOCALS" ]]; then
        echo "PASS"
    else
        echo "FAIL: No vocals.wav produced"
        exit 1
    fi
else
    echo "FAIL: Demucs separation failed"
    exit 1
fi

echo "=== Demucs: PASS ==="
