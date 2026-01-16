#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Setup Python Path to include graph_memory src
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

if [[ "$1" == "archive" ]]; then
    shift
fi

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 [archive] <transcript.json>" >&2
    exit 1
fi

python3 "${SCRIPT_DIR}/archive_episode.py" "$@"
