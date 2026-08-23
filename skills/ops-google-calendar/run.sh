#!/usr/bin/env bash
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "sanity" ]]; then
  shift
  exec uv run --quiet --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/sanity.py" "$@"
fi

exec uv run --quiet --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/manager.py" "$@"
