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

# The local proxy is configured with its deployment master key, not the
# historical development default. Resolve that credential once so every
# create-evidence-case module uses the same authenticated SciLLM lane.
if [[ -z "${SCILLM_API_KEY:-}" ]]; then
    SCILLM_RESOLVED_KEY="${SCILLM_MASTER_KEY:-${LITELLM_MASTER_KEY:-}}"
    SCILLM_ENV_FILE="${SCILLM_ENV_FILE:-${SCILLM_ROOT:-$HOME/workspace/experiments/scillm}/.env}"
    if [[ -z "$SCILLM_RESOLVED_KEY" && -f "$SCILLM_ENV_FILE" ]]; then
        for key_name in SCILLM_MASTER_KEY LITELLM_MASTER_KEY; do
            SCILLM_RESOLVED_KEY="$(sed -n "s/^${key_name}=//p" "$SCILLM_ENV_FILE" | tail -n 1)"
            SCILLM_RESOLVED_KEY="${SCILLM_RESOLVED_KEY#\"}"
            SCILLM_RESOLVED_KEY="${SCILLM_RESOLVED_KEY%\"}"
            [[ -n "$SCILLM_RESOLVED_KEY" ]] && break
        done
    fi
    SCILLM_RESOLVED_KEY="${SCILLM_RESOLVED_KEY:-${SCILLM_PROXY_KEY:-}}"
    if [[ -n "$SCILLM_RESOLVED_KEY" ]]; then
        export SCILLM_API_KEY="$SCILLM_RESOLVED_KEY"
        export SCILLM_PROXY_KEY="$SCILLM_RESOLVED_KEY"
    fi
    unset SCILLM_RESOLVED_KEY
fi

# Make graph_memory importable for direct API calls (5ms vs 5000ms subprocess)
MEMORY_SRC="${MEMORY_SRC:-${HOME}/workspace/experiments/memory/src}"
export PYTHONPATH="${MEMORY_SRC}:${PYTHONPATH:-}"

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/evidence_case.py" "$@"
