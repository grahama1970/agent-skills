#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DATA_DIR="${HOME}/.pi/consume-book"
REGISTRY_PATH="${DATA_DIR}/registry.json"
NOTES_DIR="${DATA_DIR}/notes"
BOOKMARKS_PATH="${DATA_DIR}/bookmarks.json"
CACHE_DIR="${DATA_DIR}/cache"

mkdir -p "${DATA_DIR}" "${NOTES_DIR}" "${CACHE_DIR}"

# Add skills parent dir so both consume_common and this skill are importable
export PYTHONPATH="${SCRIPT_DIR}/..${PYTHONPATH:+:$PYTHONPATH}"

# Rename mapping: directory is consume-book but Python expects consume_book
# We run scripts directly rather than as modules to avoid naming issues
run_py() {
    python "${SCRIPT_DIR}/$1" "${@:2}"
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
    bookmark)
        shift
        run_py position.py save "$@"
        ;;
    resume)
        shift
        run_py position.py resume "$@"
        ;;
    info)
        echo "Consume Book Skill - Search and track ingested books"
        echo "Registry: ${REGISTRY_PATH}"
        echo "Notes: ${NOTES_DIR}"
        echo "Bookmarks: ${BOOKMARKS_PATH}"
        echo "Cache: ${CACHE_DIR}"
        ;;
    *)
        echo "Usage: $0 {sync|search|note|notes|list|bookmark|resume|info}"
        echo ""
        echo "Commands:"
        echo "  sync [--books-dir <dir>]                        Import books"
        echo "  search <query> [--book <id>] [--context <n>]     Search text"
        echo "  note --book <id> --char-position <n> --note <t>  Add note"
        echo "  notes [--book <id>] [--agent <id>] [--json]      List notes"
        echo "  list [--json]                                   List books"
        echo "  bookmark --book <id> --char-position <n>         Save position"
        echo "  resume --book <id>                               Show position"
        echo "  info                                             Show paths"
        exit 1
        ;;
esac
