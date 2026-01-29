#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure virtual environment exists
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    echo "[review-story] Creating virtual environment..."
    uv venv "$SCRIPT_DIR/.venv"
fi

# Run the orchestrator
exec uv run --directory "$SCRIPT_DIR" python orchestrator.py "$@"
