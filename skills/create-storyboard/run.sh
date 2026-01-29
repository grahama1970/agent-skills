#!/bin/bash
# Entry point for create-storyboard skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure venv exists
if [ ! -d ".venv" ]; then
    uv venv .venv
    uv pip install typer pillow
fi

# Run orchestrator
uv run python orchestrator.py "$@"
