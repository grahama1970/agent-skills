#!/usr/bin/env bash
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

# Ensure virtual environment exists
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    echo "[taxonomy] Creating virtual environment..."
    uv venv "$SCRIPT_DIR/.venv"
fi

# Route subcommands
case "${1:-}" in
    sweep)
        shift
        exec uv run --directory "$SCRIPT_DIR" python taxonomy_sweep.py "$@"
        ;;
    *)
        # Default: taxonomy extractor
        exec uv run --directory "$SCRIPT_DIR" python taxonomy.py "$@"
        ;;
esac
