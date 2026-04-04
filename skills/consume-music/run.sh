#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
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

# Global data directory per CONVENTIONS.md
DATA_DIR="${HOME}/.pi/consume-music"
REGISTRY_PATH="${DATA_DIR}/registry.json"
NOTES_DIR="${DATA_DIR}/notes"

# Ensure data directories exist
mkdir -p "${DATA_DIR}" "${NOTES_DIR}"

# Add skills parent dir so consume_common is importable as a package
export PYTHONPATH="${SCRIPT_DIR}/..${PYTHONPATH:+:$PYTHONPATH}"

# Run Python scripts directly (no uv — minimal deps: rich, json, pathlib)
run_py() {
    python "${SCRIPT_DIR}/$1" "${@:2}"
}

case "${1:-}" in
    search)
        shift
        run_py search.py "$@"
        ;;
    list)
        shift
        run_py list.py "$@"
        ;;
    sync)
        shift
        run_py ingest_bridge.py "$@"
        ;;
    note)
        shift
        run_py notes.py add "$@"
        ;;
    notes)
        shift
        run_py notes.py list "$@"
        ;;
    info)
        echo "Consume Music Skill - Search and annotate ingested music"
        echo "Registry: ${REGISTRY_PATH}"
        echo "Notes: ${NOTES_DIR}"
        echo "Source: ${HOME}/.pi/ingest-yt-history/history.jsonl"
        ;;
    *)
        echo "Usage: $0 {search|list|sync|note|notes|info}"
        echo ""
        echo "Commands:"
        echo "  search <query> [--artist <name>] [--bridge <attr>] [--limit <n>] [--json]"
        echo "  list [--json]                                List all music"
        echo "  sync [--ingest-root <dir>]                   Import from ingest-yt-history"
        echo "  note --track <id> --note <text>              Add note"
        echo "  notes [--track <id>] [--json]                List notes"
        echo "  info                                         Show paths"
        exit 1
        ;;
esac
