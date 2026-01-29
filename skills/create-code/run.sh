#!/usr/bin/env bash
# create-code: Horus coding orchestration pipeline
# Prefer uvx/uv; fallback to system python
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v uvx >/dev/null 2>&1; then
  exec uvx --with typer --with rich python3 orchestrator.py "$@"
elif command -v uv >/dev/null 2>&1; then
  exec uv run --with typer --with rich python orchestrator.py "$@"
else
  exec python3 orchestrator.py "$@"
fi
