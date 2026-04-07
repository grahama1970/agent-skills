#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${MEMORY_VENV:-/home/graham/workspace/experiments/memory/.venv}"

export PYTHONPATH="${SCRIPT_DIR}:${SCRIPT_DIR}/../create-evidence-case:${VENV}/../src:${PYTHONPATH:-}"

exec "$VENV/bin/python" -m evidence_case_lab "$@"
