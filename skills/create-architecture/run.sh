#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Keep caller-relative module and request paths intact. Heavy runtime state stays
# outside the primary checkout; sibling delegates manage their own environments.
export UV_PROJECT_ENVIRONMENT="${CREATE_ARCHITECTURE_UV_ENV:-/mnt/storage12tb/skills/create-architecture/.venv}"
export PYTHONDONTWRITEBYTECODE=1
case "${1:-}" in
    "") set -- examine "$PWD" ;;
    examine|route|render|create|list|add-component|-h|--help) ;;
    *)
        if [[ -e "$1" ]]; then
            set -- examine "$@"
        fi
        ;;
esac
exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/create_architecture.py" "$@"
