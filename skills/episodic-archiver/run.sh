#!/bin/bash
set -e

# Resolve the directory of this script, following symlinks
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$( cd -P "$( dirname "$SOURCE" )" && pwd )"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$( cd -P "$( dirname "$SOURCE" )" && pwd )"

# Memory project root (can be overridden by env)
MEMORY_ROOT="${MEMORY_ROOT:-/home/graham/workspace/experiments/memory}"

# Setup Python Path to include graph_memory src
export PYTHONPATH="${MEMORY_ROOT}/src:${PYTHONPATH:-}"


if [[ "$1" == "archive" ]]; then
    shift
fi

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 [archive] <transcript.json>" >&2
    exit 1
fi

python3 "${SCRIPT_DIR}/archive_episode.py" "$@"
