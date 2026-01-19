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

export PYTHONPATH="${MEMORY_ROOT}/src:${PYTHONPATH:-}"

JSON_HELPER="${SCRIPT_DIR}/../json_utils.py"
ORIG_ARGS=("$@")
SKIP_SERVICE=0

# Handle 'serve' command
if [[ "$1" == "serve" ]]; then
    shift
    exec uvicorn graph_memory.service:app --reload "$@"
fi

# Fallback to python CLI
python3 -m graph_memory.agent_cli "${ORIG_ARGS[@]}"
