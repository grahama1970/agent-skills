#!/usr/bin/env bash
#
# Embedding Skill - Launcher
#
# Usage:
#   ./run.sh serve              Start FastAPI server (runs forever)
#   ./run.sh embed --text "q"   Embed text
#   ./run.sh info               Show configuration
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PORT=8602
PORT_FILE="${SCRIPT_DIR}/.port"

# Function to find free port
find_free_port() {
    local port=$1
    while lsof -i :$port >/dev/null 2>&1 || nc -z 127.0.0.1 $port >/dev/null 2>&1; do
        echo "Port $port is in use, trying next..." >&2
        ((port++))
    done
    echo $port
}

# Only hunt for port if "serve" command is used
if [[ "$1" == "serve" ]]; then
    if [ -n "${EMBEDDING_PORT:-}" ]; then
        PORT="$EMBEDDING_PORT"
    else
        echo "Finding free port starting from $DEFAULT_PORT..." >&2
        PORT=$(find_free_port $DEFAULT_PORT)
    fi
    echo "Selected Port: $PORT" >&2
    echo "$PORT" > "$PORT_FILE"
    export EMBEDDING_PORT="$PORT"
fi

# Use uv run to automatically install deps from pyproject.toml
exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/embed.py" "$@"
