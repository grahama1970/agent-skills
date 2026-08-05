#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/monitor-herdr/.venv}"
UV_BIN="${UV_BIN:-${HOME}/.local/bin/uv}"
if [[ ! -x "$UV_BIN" ]]; then
  UV_BIN="uv"
fi
case "${1:-}" in
    attach-tau-run|tau-status)
        exec "$UV_BIN" run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/tau_projection_client.py" "$@"
        ;;
esac
exec "$UV_BIN" run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/monitor_herdr.py" "$@"
