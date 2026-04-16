#!/usr/bin/env bash
# Entry point for SFX catalog system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure venv exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run 'uv sync' first."
    exit 1
fi

# Run CLI with all arguments
exec .venv/bin/python -m src.cli "$@"
