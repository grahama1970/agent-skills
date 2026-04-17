#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
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
cd "$(dirname "$0")"

# Create venv if needed
if [[ ! -d .venv ]]; then
    uv venv .venv
fi

PYTHON_BIN=".venv/bin/python"

# Ensure required runtime deps exist; install package if missing/broken.
if ! "$PYTHON_BIN" -c "import pydantic, task_monitor" >/dev/null 2>&1; then
    uv pip install --python "$PYTHON_BIN" -e .
fi

# Run the task-monitor Typer CLI.
"$PYTHON_BIN" monitor.py "$@"
