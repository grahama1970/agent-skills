#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
# Support both explicit MEMORY_ROOT and $HOME-relative path
MEMORY_ROOT="${MEMORY_ROOT:-$HOME/workspace/experiments/memory}"
DEFAULT_MEMORY_API_URL="${DEFAULT_MEMORY_API_URL:-http://127.0.0.1:8601}"

# Enforce the Docker-backed memory API as the only supported service path.
if [[ -z "${MEMORY_SERVICE_URL:-}" && -z "${MEMORY_API_URL:-}" && -z "${MEMORY_SERVER_URL:-}" ]]; then
    export MEMORY_SERVICE_URL="$DEFAULT_MEMORY_API_URL"
fi
for _var in MEMORY_SERVICE_URL MEMORY_API_URL MEMORY_SERVER_URL; do
    _value="${!_var:-}"
    if [[ -n "$_value" && ( "$_value" == unix://* || "$_value" == http+unix://* ) ]]; then
        export MEMORY_SERVICE_URL="$DEFAULT_MEMORY_API_URL"
        unset MEMORY_API_URL MEMORY_SERVER_URL
        break
    fi
done

# The user confirmed .pi/skills/memory IS graph-memory
# usage: ./run.sh serve | ./run.sh recall "query"

if [[ "$1" == "serve" ]]; then
    shift
    # Run uvicorn in the memory project environment
    export PYTHONPATH="$MEMORY_ROOT/src"
    exec uv run --directory "$MEMORY_ROOT" --all-extras uvicorn graph_memory.service.app:app "$@"
fi

# Multiplex between legacy graph_memory and new horus_lore_cli
case "$1" in
    assess)
        shift
        exec python3 "$SCRIPT_DIR/scripts/assess_usage.py" "$@"
        ;;
    chain-learn)
        shift
        export PYTHONPATH="$MEMORY_ROOT/src"
        exec uv run --directory "$MEMORY_ROOT" --all-extras python -m graph_memory.lessons.skill_chains learn "$@"
        ;;
    chain-recall)
        shift
        export PYTHONPATH="$MEMORY_ROOT/src"
        exec uv run --directory "$MEMORY_ROOT" --all-extras python -m graph_memory.lessons.skill_chains recall "$@"
        ;;
    chain-bootstrap)
        shift
        export PYTHONPATH="$MEMORY_ROOT/src"
        exec uv run --directory "$MEMORY_ROOT" --all-extras python -m graph_memory.lessons.skill_chains bootstrap "$@"
        ;;
    chain-stats)
        shift
        export PYTHONPATH="$MEMORY_ROOT/src"
        exec uv run --directory "$MEMORY_ROOT" --all-extras python -m graph_memory.lessons.skill_chains stats "$@"
        ;;
    preset|youtube|audiobook|status|persona|apply-enrichment|query)
        # Run local Horus Lore CLI
        # Ensure current dir is in PYTHONPATH for local modules like preset_storage
        export PYTHONPATH="${SCRIPT_DIR}:${MEMORY_ROOT}/src:${PYTHONPATH:-}"
        exec uv run --directory "${SCRIPT_DIR}" --no-project python3 "${SCRIPT_DIR}/horus_lore_cli.py" "$@"
        ;;
    learn)
        # Pre-commit quality gate: score memory before storing
        # Extract --problem and --solution from args for quality check
        _PROBLEM="" _SOLUTION="" _SCOPE="" _REMAINING_ARGS=()
        shift  # consume 'learn'
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --problem|-p) _PROBLEM="$2"; _REMAINING_ARGS+=("$1" "$2"); shift 2 ;;
                --solution|-s) _SOLUTION="$2"; _REMAINING_ARGS+=("$1" "$2"); shift 2 ;;
                --scope) _SCOPE="$2"; _REMAINING_ARGS+=("$1" "$2"); shift 2 ;;
                *) _REMAINING_ARGS+=("$1"); shift ;;
            esac
        done

        # Run quality scorer as pre-check (non-blocking — warns but does not reject)
        if [[ -n "$_PROBLEM" || -n "$_SOLUTION" ]]; then
            _TEXT="${_PROBLEM} ${_SOLUTION}"
            export PYTHONPATH="${SCRIPT_DIR}:${SCRIPT_DIR}/../common:${PYTHONPATH:-}"
            python3 -c "
import sys, json
try:
    from memory_quality_scorer import score_memory
    r = score_memory(text='''${_TEXT//\'/\\\'}''', scope='${_SCOPE}', check_contradiction=False)
    meta = r.to_metadata()
    score = meta.get('_quality_score', 0)
    if r.content_quality == 'ambiguous':
        print(f'[quality-gate] WARNING: Memory scored as AMBIGUOUS (score={score})', file=sys.stderr)
        print(f'[quality-gate] Deficits: {r.deficits}', file=sys.stderr)
    elif score < 0.3:
        print(f'[quality-gate] WARNING: Low quality score={score}, deficits={r.deficits}', file=sys.stderr)
    else:
        print(f'[quality-gate] OK quality={score} content={r.content_quality}', file=sys.stderr)
except Exception as e:
    print(f'[quality-gate] Skipped: {e}', file=sys.stderr)
" || true
        fi

        # Pass through to graph_memory learn command
        export PYTHONPATH="$MEMORY_ROOT/src"
        exec uv run --directory "$MEMORY_ROOT" --all-extras python -m graph_memory.agent_cli learn "${_REMAINING_ARGS[@]}"
        ;;
    *)
        # Run legacy Graph Memory CLI (handles 'recall', 'serve', etc.)
        # Layout defaults: auto with rollback via MEMORY_LAYOUT=vanilla
        export PYTHONPATH="$MEMORY_ROOT/src"
        exec uv run --directory "$MEMORY_ROOT" --all-extras python -m graph_memory.agent_cli "$@"
        ;;
esac
