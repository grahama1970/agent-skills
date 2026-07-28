#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UV_BIN="${UV_BIN:-${HOME}/.local/bin/uv}"
if [[ ! -x "$UV_BIN" ]]; then
  UV_BIN="uv"
fi
exec "$UV_BIN" run --project "$SCRIPT_DIR" python3 "$SCRIPT_DIR/scripts/project_watchdog.py" "$@"
