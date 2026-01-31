#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Global data directory per CONVENTIONS.md
DATA_DIR="${HOME}/.pi/consume-movie"
REGISTRY_PATH="${DATA_DIR}/registry.json"
NOTES_DIR="${DATA_DIR}/notes"
CLIPS_DIR="${DATA_DIR}/clips"

# Ensure data directories exist
mkdir -p "${DATA_DIR}" "${NOTES_DIR}" "${CLIPS_DIR}"

# Add skills parent dir so consume_common is importable as a package
export PYTHONPATH="${SCRIPT_DIR}/..${PYTHONPATH:+:$PYTHONPATH}"

# Run Python scripts via uv for proper dependency management
run_py() {
    uv run --directory "$SCRIPT_DIR" python "${SCRIPT_DIR}/$1" "${@:2}"
}

# Main CLI
case "$1" in
    search)
        shift
        run_py search.py "$@"
        ;;
    clip)
        shift
        run_py clips.py "$@"
        ;;
    note)
        shift
        run_py notes.py add "$@"
        ;;
    notes)
        shift
        run_py notes.py list "$@"
        ;;
    list)
        shift
        run_py list.py "$@"
        ;;
    sync)
        shift
        run_py ingest_bridge.py "$@"
        ;;
    watch)
        # New command: watch with book context
        shift
        run_py watch.py "$@"
        ;;
    info)
        echo "Consume Movie Skill - Search and extract from ingested movies"
        echo "Registry: ${REGISTRY_PATH}"
        echo "Notes: ${NOTES_DIR}"
        echo "Clips: ${CLIPS_DIR}"
        ;;
    *)
        echo "Usage: $0 {search|clip|note|notes|list|sync|watch|info}"
        echo ""
        echo "Commands:"
        echo "  search <query> [--movie <id>] [--with-book-context]  Search subtitles"
        echo "  clip --query <text> --output <dir> [--with-book-context]  Extract clip"
        echo "  note --movie <id> --timestamp <sec> --note <text>  Add note"
        echo "  notes [--movie <id>] [--json]                     List notes"
        echo "  list [--json]                                     List movies"
        echo "  sync                                              Import from ingest-movie"
        echo "  watch --movie <id> [--with-book-context] [--with-reviews] [--acquire-books]"
        echo "        Watch movie with book context, reviews, and auto-acquire missing books"
        echo "  info                                              Show paths"
        echo ""
        echo "Context Options:"
        echo "  --with-book-context  Load notes from related book before processing"
        echo "  --with-reviews       Fetch external reviews via /dogpile"
        echo "  --acquire-books      Auto-add missing books to Readarr"
        exit 1
        ;;
esac