#!/usr/bin/env bash
# Run the ops-linkedin CLI in its skill-local Python project.
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${OPS_LINKEDIN_USE_SYSTEM_PYTHON:-0}" == "1" ]]; then
  # Offline/test-only source bootstrap when the uv project cannot be installed.
  export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
  exec python3 -m ops_linkedin.cli "$@"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "ops-linkedin requires uv; install uv or set OPS_LINKEDIN_USE_SYSTEM_PYTHON=1" >&2
  exit 127
fi

exec uv run --project "$SCRIPT_DIR" python -m ops_linkedin.cli "$@"
