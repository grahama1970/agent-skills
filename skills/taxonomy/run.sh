#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure virtual environment exists
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    echo "[taxonomy] Creating virtual environment..."
    uv venv "$SCRIPT_DIR/.venv"
fi

# Run the taxonomy extractor
exec uv run --directory "$SCRIPT_DIR" python taxonomy.py "$@"
