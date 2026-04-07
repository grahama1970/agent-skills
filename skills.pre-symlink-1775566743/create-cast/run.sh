#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Character casting orchestrator for Horus movie pipeline

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'


PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
cd "$SCRIPT_DIR"

# Ensure dependencies
if ! command -v uv &>/dev/null; then
    echo "ERROR: uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Sync dependencies if needed
if [[ ! -d ".venv" ]]; then
    uv sync --quiet
fi

CMD="${1:-help}"
shift || true

case "$CMD" in
    start)
        uv run python -m create_cast.cli start "$@"
        ;;
    continue)
        uv run python -m create_cast.cli continue-session "$@"
        ;;
    status)
        uv run python -m create_cast.cli status "$@"
        ;;
    export)
        uv run python -m create_cast.cli export-packs "$@"
        ;;
    list)
        uv run python -m create_cast.cli list-sessions "$@"
        ;;
    sanity)
        ./sanity/sanity.sh
        ;;
    help|--help|-h)
        echo "create-cast: Character casting for Horus movies"
        echo ""
        echo "Commands:"
        echo "  start <script.json>  Start new casting session"
        echo "  continue             Continue session with answers"
        echo "  status               Check session status"
        echo "  export               Export identity packs"
        echo "  list                 List all sessions"
        echo "  sanity               Run sanity checks"
        echo ""
        echo "Options:"
        echo "  --session ID         Session ID to operate on"
        echo "  --answers JSON       JSON answers to questions"
        echo "  --output DIR         Output directory for export"
        echo "  --json               Output as JSON"
        echo "  --auto-approve       Skip questions, use defaults"
        echo ""
        echo "Examples:"
        echo "  ./run.sh start script.json"
        echo "  ./run.sh continue --session casting-xxx --answers '{\"q1\": \"approve\"}'"
        echo "  ./run.sh export --session casting-xxx --output ./characters"
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
