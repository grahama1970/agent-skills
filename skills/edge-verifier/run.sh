#!/bin/bash
set -euo pipefail

# Get directory of this script
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROJECT_ROOT="$(realpath "${SCRIPT_DIR}/../../..")"

# Setup Python Path to include graph_memory src
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

python3 "${SCRIPT_DIR}/verify_edges.py" "$@"
