#!/usr/bin/env bash
#
# QRA Skill Runner
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Add local scillm to PYTHONPATH if SCILLM_PATH is set (legacy overriding)
if [[ -n "${SCILLM_PATH:-}" && -d "${SCILLM_PATH}" ]]; then
    export PYTHONPATH="${SCILLM_PATH}:${PYTHONPATH:-}"
fi

# Use uv run to execute in project environment
# Git dependency on scillm in pyproject.toml handles standard cases
exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/qra.py" "$@"
