#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Run figure-lab skill — dispatches to figure_lab.py typer CLI or GUI.
#
# Usage:
#   ./run.sh compose --type bar --data sample.json
#   ./run.sh evaluate --input gallery/bar_v1.html
#   ./run.sh promote --input gallery/bar_v1.html
#   ./run.sh gallery
#   ./run.sh catalog-status
#   ./run.sh backlog
#   ./run.sh gui          # launch PySide6/QML app
#   ./run.sh app          # alias for gui
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
cd "$SCRIPT_DIR"

case "${1:-}" in
    gui|app)
        shift
        exec uv run --project "$SCRIPT_DIR" python app.py "$@"
        ;;
    *)
        exec uv run --project "$SCRIPT_DIR" python figure_lab.py "$@"
        ;;
esac
