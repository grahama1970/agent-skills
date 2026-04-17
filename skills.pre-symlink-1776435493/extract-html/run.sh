#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Entry point for html-to-schema skill
# Usage: ./run.sh convert --html <file> --schema <schema> ...

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

# Ensure we are in the skill directory
cd "$(dirname "$0")"

# Use uv to run the cli
if ! command -v uv &> /dev/null; then
    echo "Error: uv is required but not installed."
    exit 1
fi

# Run the CLI
# explicit python path to ensure we use the venv created by uv sync if needed, 
# or just let uv run handle ephemeral venv
uv run python -m extract_html.cli "$@"
