#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# GitHub Search - Deep multi-strategy search for repositories and code
set -euo pipefail

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

# Ensure virtual environment exists
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    echo "Creating virtual environment..." >&2
    python3 -m venv "$SCRIPT_DIR/.venv"
    "$SCRIPT_DIR/.venv/bin/pip" install -q typer rich
fi

# Run the main script with PYTHONPATH set for package imports
PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}" exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/github_search.py" "$@"
