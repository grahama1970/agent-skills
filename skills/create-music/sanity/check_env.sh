#!/usr/bin/env bash
#
# Environment sanity check for create-music skill
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# Use venv Python via uv
UV_PYTHON="uv run --project ${SKILL_DIR} python"

echo "=== create-music Environment Check ==="

# Check ffmpeg
echo -n "ffmpeg: "
if command -v ffmpeg &>/dev/null; then
    ffmpeg -version | head -1
else
    echo "NOT FOUND"
    exit 1
fi

# Check Python
echo -n "Python: "
${UV_PYTHON} --version

# Check torch
echo -n "torch: "
${UV_PYTHON} -c "import torch; print(f'{torch.__version__} (CUDA: {torch.cuda.is_available()})')" 2>/dev/null || echo "NOT INSTALLED"

# Check torchaudio
echo -n "torchaudio: "
${UV_PYTHON} -c "import torchaudio; print(torchaudio.__version__)" 2>/dev/null || echo "NOT INSTALLED"

# Check demucs
echo -n "demucs: "
${UV_PYTHON} -c "import demucs; print('installed')" 2>/dev/null || echo "NOT INSTALLED"

# Check soundfile
echo -n "soundfile: "
${UV_PYTHON} -c "import soundfile; print(soundfile.__version__)" 2>/dev/null || echo "NOT INSTALLED"

# Check audiocraft (optional)
echo -n "audiocraft: "
${UV_PYTHON} -c "import audiocraft; print('installed')" 2>/dev/null || echo "not installed (optional)"

# Check audio-separator (optional)
echo -n "audio-separator: "
${UV_PYTHON} -c "import audio_separator; print('installed')" 2>/dev/null || echo "not installed (optional)"

# GPU info
echo ""
echo "=== GPU Info ==="
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader
else
    echo "No NVIDIA GPU detected"
fi

echo ""
echo "=== Environment Check Complete ==="
