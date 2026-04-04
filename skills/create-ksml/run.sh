#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# create-ksml execution script

# Resolve adapter path
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
ADAPTER="$SCRIPT_DIR/adapter.py"

# Pass arguments to adapter
uv run --script "$ADAPTER" "$@"
