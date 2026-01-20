#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$1" == "archive" ]]; then
    shift
fi

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 [archive] <transcript.json>" >&2
    exit 1
fi

# Use uv run with project environment
exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/archive_episode.py" "$@"
