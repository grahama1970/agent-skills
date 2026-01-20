#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORY_ROOT="${MEMORY_ROOT:-/home/graham/workspace/experiments/memory}"

# The user confirmed .pi/skills/memory IS graph-memory
# usage: ./run.sh serve | ./run.sh recall "query"

if [[ "$1" == "serve" ]]; then
    shift
    # Run uvicorn in the memory project environment
    exec uv run --directory "$MEMORY_ROOT" --all-extras uvicorn graph_memory.service.app:app --reload "$@"
fi

# Run the CLI
exec uv run --directory "$MEMORY_ROOT" --all-extras python -m graph_memory.agent_cli "$@"
