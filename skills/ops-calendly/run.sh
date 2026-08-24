#!/usr/bin/env bash
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/ops-calendly/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"

if [[ "${1:-}" == "sanity" ]]; then
  shift
  exec uv run --quiet --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/sanity.py" "$@"
fi

exec uv run --quiet --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/ops_calendly.py" "$@"
