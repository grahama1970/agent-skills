#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
LOCAL_DEV="${ANVIL_DEV_DIR:-}"
if [ -d "$LOCAL_DEV" ]; then
    cd "$LOCAL_DEV" || exit
    exec uv run anvil "$@"
else
    exec uvx --from "git+https://github.com/grahama1970/anvil.git" anvil "$@"
fi
