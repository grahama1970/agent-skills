#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts
unset VIRTUAL_ENV
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-help}" in
  search)
    shift
    exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/search.py" "$@"
    ;;
  ingest)
    shift
    exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/ingest.py" "$@"
    ;;
  help|--help|-h)
    echo "Usage: ./run.sh <command>"
    echo "  search  --key KEY --bpm N --instrument NAME --mood TAGS"
    echo "  ingest  --stem-dir DIR --source-song TITLE --artist NAME"
    ;;
  *)
    echo "Unknown: $1"; exit 1 ;;
esac
