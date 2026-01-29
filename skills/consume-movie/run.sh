#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Global data directory per CONVENTIONS.md
DATA_DIR="${HOME}/.pi/consume-movie"
REGISTRY_PATH="${DATA_DIR}/registry.json"
NOTES_DIR="${DATA_DIR}/notes"
CLIPS_DIR="${DATA_DIR}/clips"

# Ensure data directories exist
mkdir -p "${DATA_DIR}" "${NOTES_DIR}" "${CLIPS_DIR}"

# Add consume-common to Python path
export PYTHONPATH="${SCRIPT_DIR}/../consume-common:${PYTHONPATH}"

# Main CLI
case "$1" in
    search)
        shift
        python -m consume_movie.search "$@"
        ;;
    clip)
        shift
        python -m consume_movie.clips "$@"
        ;;
    note)
        shift
        python -m consume_movie.notes "$@"
        ;;
    list)
        python -m consume_movie.list "$@"
        ;;
    sync)
        python -m consume_movie.ingest_bridge "$@"
        ;;
    info)
        echo "Consume Movie Skill - Search and extract from ingested movies"
        echo "Registry: ${REGISTRY_PATH}"
        echo "Notes: ${NOTES_DIR}"
        echo "Clips: ${CLIPS_DIR}"
        ;;
    *)
        echo "Usage: $0 {search|clip|note|list|sync|info}"
        echo ""
        echo "Commands:"
        echo "  search <query> [--movie <id>] [--context <sec>]  Search subtitles"
        echo "  clip --query <text> --output <dir>              Extract video clip"
        echo "  note --movie <id> --timestamp <sec> --note <text>  Add note"
        echo "  list [--json]                                   List movies"
        echo "  sync                                            Import from ingest-movie"
        echo "  info                                            Show paths"
        exit 1
        ;;
esac