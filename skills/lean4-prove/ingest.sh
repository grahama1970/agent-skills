#!/bin/bash
set -eo pipefail

# Ingest DeepSeek-Prover-V1 dataset into memory for retrieval-augmented proving
# Uses the memory project's Python environment which has arango + datasets installed

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORY_ROOT="${MEMORY_ROOT:-$HOME/workspace/experiments/memory}"

# Set HuggingFace cache to user directory
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_DATASETS_CACHE="${HF_DATASETS_CACHE:-$HOME/.cache/huggingface/datasets}"
# Disable hf_transfer if not installed (slower but works)
export HF_HUB_ENABLE_HF_TRANSFER=0

# Install datasets if needed (one-time)
if ! uv run --directory "$MEMORY_ROOT" python -c "import datasets" 2>/dev/null; then
    echo "Installing datasets package..."
    uv pip install --directory "$MEMORY_ROOT" datasets huggingface_hub
fi

# Run ingest script in memory environment
exec uv run --directory "$MEMORY_ROOT" --all-extras python "$SCRIPT_DIR/ingest_prover_v1.py" "$@"
