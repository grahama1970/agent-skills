#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env from project root
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Make graph_memory importable for direct API calls (5ms vs 5000ms subprocess)
MEMORY_SRC="${MEMORY_SRC:-/home/graham/workspace/experiments/memory/src}"
export PYTHONPATH="${MEMORY_SRC}:${PYTHONPATH:-}"

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/evidence_case.py" "$@"
