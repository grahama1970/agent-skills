#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v uv >/dev/null 2>&1; then
  if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    uv venv .venv
    uv pip install typer
  fi
  exec uv run python scripts/cli.py "$@"
fi

export PYTHONPATH="${SCRIPT_DIR}/scripts${PYTHONPATH:+:$PYTHONPATH}"
exec python3 scripts/cli.py "$@"
