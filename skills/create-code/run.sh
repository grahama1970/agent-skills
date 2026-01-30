#!/usr/bin/env bash
# create-code: Horus coding orchestration pipeline
# Prefer uvx/uv; fallback to system python
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v uvx >/dev/null 2>&1; then
  exec uvx --with typer --with rich python3 "$SCRIPT_DIR/orchestrator.py" "$@"
elif command -v uv >/dev/null 2>&1; then
  exec uv run --with typer --with rich python "$SCRIPT_DIR/orchestrator.py" "$@"
else
  exec python3 "$SCRIPT_DIR/orchestrator.py" "$@"
fi
