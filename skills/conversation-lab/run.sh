#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env files
if [ -f "$SCRIPT_DIR/.env" ]; then set -a; source "$SCRIPT_DIR/.env"; set +a; fi
if [ -f "$SCRIPT_DIR/../../.env" ]; then set -a; source "$SCRIPT_DIR/../../.env"; set +a; fi

CMD="${1:-help}"

case "$CMD" in
    gui|app)
        shift || true
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/app.py" "$@"
        ;;
    *)
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/conversation_lab.py" "$@"
        ;;
esac
