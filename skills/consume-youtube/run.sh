#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DATA_DIR="${HOME}/.pi/consume-youtube"
REGISTRY_PATH="${DATA_DIR}/registry.json"
NOTES_DIR="${DATA_DIR}/notes"
INDICES_DIR="${DATA_DIR}/indices"

mkdir -p "${DATA_DIR}" "${NOTES_DIR}" "${INDICES_DIR}"

export PYTHONPATH="${SCRIPT_DIR}/../consume-common:${PYTHONPATH}"

case "$1" in
    sync)
        shift
        python -m consume_youtube.ingest_bridge "$@"
        ;;
    search)
        shift
        python -m consume_youtube.search "$@"
        ;;
    note)
        shift
        python -m consume_youtube.notes "$@"
        ;;
    list)
        python -m consume_youtube.list "$@"
        ;;
    index)
        shift
        python -m consume_youtube.indexer "$@"
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
