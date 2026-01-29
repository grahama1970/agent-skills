#!/usr/bin/env bash
# One-time setup for GPU-accelerated transcription
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Setting up faster-whisper (GPU) environment..."

if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    python3 -m venv "$SCRIPT_DIR/.venv"
    echo "    Created virtual environment"
fi

source "$SCRIPT_DIR/.venv/bin/activate"

pip install -q -U pip
pip install -q faster-whisper

echo "==> GPU Setup Complete!"
echo ""
echo "GPU Info:"
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader

echo ""
echo "To use GPU transcription:"
echo "  ./run.sh ingest-gpu <filename>"
echo "  ./run.sh ingest-all-gpu"
