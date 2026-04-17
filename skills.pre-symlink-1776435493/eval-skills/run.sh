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

case "${1:-eval}" in
    eval)
        # Strip the "eval" subcommand if present, pass remaining args
        [ "${1:-}" = "eval" ] && shift
        exec uv run --directory "$SCRIPT_DIR" python eval_runner.py "$@"
        ;;
    *)
        exec uv run --directory "$SCRIPT_DIR" python eval_runner.py "$@"
        ;;
esac
