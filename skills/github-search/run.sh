#!/usr/bin/env bash
# GitHub Search - Deep multi-strategy search for repositories and code
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure virtual environment exists
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    echo "Creating virtual environment..." >&2
    python3 -m venv "$SCRIPT_DIR/.venv"
    "$SCRIPT_DIR/.venv/bin/pip" install -q typer rich
fi

# Run the main script with PYTHONPATH set for package imports
PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}" exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/github_search.py" "$@"
