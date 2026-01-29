#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DATA_DIR="${HOME}/.pi/consume-book"
REGISTRY_PATH="${DATA_DIR}/registry.json"
NOTES_DIR="${DATA_DIR}/notes"
BOOKMARKS_PATH="${DATA_DIR}/bookmarks.json"
CACHE_DIR="${DATA_DIR}/cache"

mkdir -p "${DATA_DIR}" "${NOTES_DIR}" "${CACHE_DIR}"

export PYTHONPATH="${SCRIPT_DIR}/../consume-common:${PYTHONPATH}"

case "$1" in
    sync)
        shift
        python -m consume_book.ingest_bridge "$@"
        ;;
    search)
        shift
        python -m consume_book.search "$@"
        ;;
    note)
        shift
        python -m consume_book.notes "$@"
        ;;
    list)
        python -m consume_book.list "$@"
        ;;
    bookmark)
        shift
        python -m consume_book.position save "$@"
        ;;
    resume)
        shift
        python -m consume_book.position resume "$@"
        ;;
    info)
        echo "Consume Book Skill - Search and track ingested books"
        echo "Registry: ${REGISTRY_PATH}"
        echo "Notes: ${NOTES_DIR}"
        echo "Bookmarks: ${BOOKMARKS_PATH}"
        echo "Cache: ${CACHE_DIR}"
        ;;
    *)
        echo "Usage: $0 {sync|search|note|list|bookmark|resume|info}"
        echo ""
        echo "Commands:"
        echo "  sync [--books-dir <dir>]                        Import books"
        echo "  search <query> [--book <id>] [--context <n>]     Search text"
        echo "  note --book <id> --char-position <n> --note <t>  Add note"
        echo "  list [--json]                                   List books"
        echo "  bookmark --book <id> --char-position <n>         Save position"
        echo "  resume --book <id>                               Show position"
        echo "  info                                             Show paths"
        exit 1
        ;;
esac
