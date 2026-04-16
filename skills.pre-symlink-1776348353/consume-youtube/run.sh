#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -e

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

DATA_DIR="${HOME}/.pi/consume-youtube"
REGISTRY_PATH="${DATA_DIR}/registry.json"
NOTES_DIR="${DATA_DIR}/notes"
INDICES_DIR="${DATA_DIR}/indices"

mkdir -p "${DATA_DIR}" "${NOTES_DIR}" "${INDICES_DIR}"

# Add skills parent dir so both consume_common and this skill are importable
export PYTHONPATH="${SCRIPT_DIR}/..${PYTHONPATH:+:$PYTHONPATH}"

run_py() {
    python3 "${SCRIPT_DIR}/$1" "${@:2}"
}

case "$1" in
    sync)
        shift
        run_py ingest_bridge.py "$@"
        ;;
    search)
        shift
        run_py search.py "$@"
        ;;
    note)
        shift
        run_py notes.py "$@"
        ;;
    list)
        shift
        run_py list.py "$@"
        ;;
    index)
        shift
        run_py indexer.py "$@"
        ;;
    info)
        echo "Consume YouTube Skill - Search and annotate ingested transcripts"
        echo "Registry: ${REGISTRY_PATH}"
        echo "Notes: ${NOTES_DIR}"
        echo "Indices: ${INDICES_DIR}"
        ;;
    *)
        echo "Usage: $0 {sync|search|note|list|index|info}"
        echo ""
        echo "Commands:"
        echo "  sync [--ingest-root <dir>]                      Import transcripts"
        echo "  search <query> [--channel <name>] [--video <id>] Search transcripts"
        echo "  note --video <id> --timestamp <sec> --note <t>   Add note"
        echo "  list [--json] [--channel <name>]                List videos"
        echo "  index --channel <name>                           Build index"
        echo "  info                                             Show paths"
        exit 1
        ;;
esac
