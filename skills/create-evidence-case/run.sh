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

# SciLLM owns its rotating proxy key. Load it for this composed skill when the
# caller has not supplied an explicit API key.
SCILLM_ENV="${SCILLM_ENV:-${HOME}/workspace/experiments/scillm/.env}"
if [ -z "${SCILLM_API_KEY:-}" ] && [ -f "$SCILLM_ENV" ]; then
    set -a
    source "$SCILLM_ENV"
    set +a
    export SCILLM_API_KEY="${SCILLM_MASTER_KEY:-${LITELLM_MASTER_KEY:-}}"
fi

# Make graph_memory importable for direct API calls (5ms vs 5000ms subprocess)
MEMORY_SRC="${MEMORY_SRC:-${HOME}/workspace/experiments/memory/src}"
export PYTHONPATH="${MEMORY_SRC}:${PYTHONPATH:-}"

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/evidence_case.py" "$@"
