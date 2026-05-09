#!/usr/bin/env bash
# project-drift skill runner
set -euo pipefail
unset VIRTUAL_ENV || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CALLER_CWD="$(pwd)"
export PROJECT_DRIFT_CWD="${PROJECT_DRIFT_CWD:-$CALLER_CWD}"

if command -v uv >/dev/null 2>&1; then
  if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    (cd "$SCRIPT_DIR" && uv venv .venv && uv pip install -e .)
  fi
  exec uv run --directory "$SCRIPT_DIR" python -m project_drift "$@"
fi

PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m project_drift "$@"
