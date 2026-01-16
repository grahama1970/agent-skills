#!/bin/bash
# Self-contained runpod-ops skill - auto-installs via uv
# Usage: ./run.sh list-instances
set -e

# Git source for runpod_ops (not on PyPI)
REPO="runpod_ops @ git+https://github.com/grahama1970/runpod_ops.git"

if command -v uv &> /dev/null; then
    # Run directly from git repo (preferred)
    uv run --from "$REPO" runpod_ops "$@"
elif [[ -n "${RUNPOD_OPS_PATH:-}" && -d "${RUNPOD_OPS_PATH}" ]]; then
    # Fallback to local install if RUNPOD_OPS_PATH is set
    source "${RUNPOD_OPS_PATH}/.venv/bin/activate"
    runpod_ops "$@"
else
    echo "Error: uv not found and RUNPOD_OPS_PATH not set" >&2
    echo "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi
