#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/agent-skills-ticket-venv}"

if ! command -v uv >/dev/null 2>&1; then
  echo "ticket: uv is required" >&2
  exit 1
fi

if [[ ! -d "$UV_PROJECT_ENVIRONMENT" ]]; then
  uv venv "$UV_PROJECT_ENVIRONMENT" >/dev/null
fi

uv sync --project "$SCRIPT_DIR" >/dev/null
exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/ticket_cli.py" "$@"
