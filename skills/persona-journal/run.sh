#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Persona Journal - Daily journal generation for personas
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

# Use the main module from memory skill
JOURNAL_MODULE="${SCRIPT_DIR}/../memory/persona_journal.py"

if [[ ! -f "$JOURNAL_MODULE" ]]; then
    echo "Error: persona_journal.py not found at $JOURNAL_MODULE"
    exit 1
fi

# Pass all args to the Python module
exec uv run --project "$SCRIPT_DIR/../memory" python "$JOURNAL_MODULE" "$@"
