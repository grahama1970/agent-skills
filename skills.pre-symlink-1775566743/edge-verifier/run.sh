#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Route subcommands
case "${1:-}" in
    verify)
        shift
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/verify_edges.py" "$@"
        ;;
    hint-sweep)
        shift
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/hint_sweep.py" "$@"
        ;;
    *)
        # Default: verify edges
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/verify_edges.py" "$@"
        ;;
esac
