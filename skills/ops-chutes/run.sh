#!/bin/bash
# Wrapper to run ops-chutes commands with uv

# Determine skill directory
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

# Ensure dependencies are installed
if [ ! -d ".venv" ]; then
    uv venv
    uv pip install .
fi

# Run the manager
uv run manager.py "$@"
