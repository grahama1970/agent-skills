#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env files
if [ -f "$SCRIPT_DIR/.env" ]; then set -a; source "$SCRIPT_DIR/.env"; set +a; fi
if [ -f "$SCRIPT_DIR/../../.env" ]; then set -a; source "$SCRIPT_DIR/../../.env"; set +a; fi

# Ensure graph_memory is importable
MEMORY_SRC="$(cd "$SCRIPT_DIR/../../../../memory/src" 2>/dev/null && pwd)" || true
if [ -n "$MEMORY_SRC" ]; then
    export PYTHONPATH="${MEMORY_SRC}:${PYTHONPATH:-}"
fi

exec uv run --project "$SCRIPT_DIR" python -m qra_review "$@"
