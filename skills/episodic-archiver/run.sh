#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -lt 1 ]]; then
    echo "Usage:"
    echo "  $0 archive <transcript.json>  - Archive a session"
    echo "  $0 list-unresolved            - List pending sessions"
    echo "  $0 resolve <session_id>       - Mark session resolved"
    exit 1
fi

# Use uv run with project environment
exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/archive_episode.py" "$@"
