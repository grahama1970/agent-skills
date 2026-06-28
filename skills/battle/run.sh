#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

unset VIRTUAL_ENV
export BATTLE_STORAGE_ROOT="${BATTLE_STORAGE_ROOT:-/mnt/storage12tb/skills/battle}"
mkdir -p "$BATTLE_STORAGE_ROOT"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$BATTLE_STORAGE_ROOT/.venv}"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
cd "$SCRIPT_DIR"

export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec uv run --project "$SCRIPT_DIR" python -m battle_skill.cli "$@"
