#!/usr/bin/env bash
# Thin wrapper. All logic lives in writing_style.py (Typer CLI).
unset VIRTUAL_ENV
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/writing-style/.venv}"
UV_BIN="${UV_BIN:-${HOME}/.local/bin/uv}"
[[ -x "$UV_BIN" ]] || UV_BIN="uv"
exec "$UV_BIN" run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/writing_style.py" "$@"
