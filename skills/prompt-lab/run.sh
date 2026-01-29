#!/bin/bash
# Prompt Lab: Systematic prompt engineering with self-correction
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Use sparta venv (has scillm installed)
SPARTA_VENV="/home/graham/workspace/experiments/sparta/.venv"
SPARTA_ENV="/home/graham/workspace/experiments/sparta/.env"

# Load environment from sparta
if [ -f "$SPARTA_ENV" ]; then
    set -a
    source "$SPARTA_ENV"
    set +a
fi

# Run with sparta venv python
exec "$SPARTA_VENV/bin/python" prompt_lab.py "$@"
