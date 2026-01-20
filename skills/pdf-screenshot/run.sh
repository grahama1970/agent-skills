#!/bin/bash
# Wrapper to run pdf-screenshot with uv
# Usage: ./run.sh path/to.pdf --page N ...

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed. Please install uv."
    exit 1
fi

# Run with uv
uv run --quiet --project "$SCRIPT_DIR" "$SCRIPT_DIR/pdf_screenshot.py" "$@"
