#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls.
unset VIRTUAL_ENV
# Unified entry point for ops-wiim (WiiM Amp low-volume diagnostics).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load repo-root .env if present (WIIM_IP override).
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
fi

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/ops_wiim.py" "$@"
