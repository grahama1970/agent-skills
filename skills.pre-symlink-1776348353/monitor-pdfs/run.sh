#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# run.sh - CLI wrapper for monitor-pdfs skill

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

# Ensure .venv exists
if [ ! -d ".venv" ]; then
    echo "Initializing virtual environment..."
    uv venv .venv
    source .venv/bin/activate
    uv pip install typer rich loguru
fi

# Run the monitor script
source .venv/bin/activate
PYTHONPATH="$SKILL_DIR" python monitor_pdfs.py "$@"
