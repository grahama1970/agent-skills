#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "verify" ]]; then
    shift
fi

# Use uv run with project environment. 
# Dependencies (graph_memory) are installed from git url in pyproject.toml
exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/verify_edges.py" "$@"
