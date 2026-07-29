#!/bin/bash
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
# Hack Skill Entry Point

# Ensure the script directory and shared repo contracts are importable.
export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/skills:${PYTHONPATH-}:$(dirname "$0")"

# Execute the python CLI
exec python3 "$(dirname "$0")/hack.py" "$@"
