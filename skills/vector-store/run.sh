#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PORT=8600
PORT_FILE="${SCRIPT_DIR}/.port"

# Function to find free port
find_free_port() {
    local port=$1
    while lsof -i :$port >/dev/null 2>&1 || nc -z 127.0.0.1 $port >/dev/null 2>&1; do
        # Check if it's OUR service already running? 
        # Hard to distinguish generically. Assume occupied = unavailable.
        echo "Port $port is in use, trying next..." >&2
        ((port++))
    done
    echo $port
}

# Allow override
if [ -n "$VECTOR_STORE_PORT" ]; then
    PORT="$VECTOR_STORE_PORT"
else
    echo "Finding free port starting from $DEFAULT_PORT..." >&2
    PORT=$(find_free_port $DEFAULT_PORT)
fi

echo "Selected Port: $PORT" >&2
echo "$PORT" > "$PORT_FILE"

# Run Uvicorn
uv run --project "${SCRIPT_DIR}" uvicorn server:app --host 0.0.0.0 --port "$PORT" --reload
