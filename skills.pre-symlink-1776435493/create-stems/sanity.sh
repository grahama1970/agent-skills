#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS  ${label}"
        ((PASS++)) || true
    else
        echo "  FAIL  ${label}"
        ((FAIL++)) || true
    fi
}

echo "=== create-stems Sanity Suite ==="
echo ""

echo "[1/4] System tools"
check "ffmpeg" command -v ffmpeg
check "ffprobe" command -v ffprobe

echo ""
echo "[2/4] Python environment"
cd "${SCRIPT_DIR}"
if [[ ! -d ".venv" ]]; then
    echo "  Creating venv..."
    uv sync --quiet 2>/dev/null || true
fi
check "uv available" command -v uv
check "python in venv" test -f "${SCRIPT_DIR}/.venv/bin/python"

echo ""
echo "[3/4] Python imports"
check "torch" uv run python -c "import torch; print(f'torch {torch.__version__}')"
check "torchaudio" uv run python -c "import torchaudio"
check "demucs" uv run python -c "import demucs.separate"
check "typer" uv run python -c "import typer"
check "loguru" uv run python -c "from loguru import logger"
check "soundfile" uv run python -c "import soundfile"

echo ""
echo "[4/4] GPU detection"
CUDA=$(uv run python -c "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')" 2>/dev/null || echo "cpu")
echo "  Device: ${CUDA}"
if [[ "${CUDA}" == "cuda" ]]; then
    GPU_NAME=$(uv run python -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null || echo "unknown")
    GPU_MEM=$(uv run python -c "import torch; print(f'{torch.cuda.get_device_properties(0).total_mem / 1e9:.1f}GB')" 2>/dev/null || echo "unknown")
    echo "  GPU: ${GPU_NAME} (${GPU_MEM})"
fi

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
[[ ${FAIL} -eq 0 ]] && exit 0 || exit 1
