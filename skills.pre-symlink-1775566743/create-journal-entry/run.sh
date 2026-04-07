#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# create-journal-entry: Nightly journal entry creation with dream pipeline integration
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SKILLS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$SKILLS_DIR")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
elif [ -f "$PROJECT_ROOT/../.env" ]; then
    set -a
    source "$PROJECT_ROOT/../.env"
    set +a
fi

# Use persona_journal.py from memory skill
JOURNAL_MODULE="${SKILLS_DIR}/memory/persona_journal.py"

if [[ ! -f "$JOURNAL_MODULE" ]]; then
    echo "Error: persona_journal.py not found at $JOURNAL_MODULE"
    echo "  The create-journal-entry skill requires the memory skill's persona_journal module."
    exit 1
fi

# Pass all args to the Python module
cd "$SKILLS_DIR/memory"
exec uv run --project "$SKILLS_DIR/memory" python "$JOURNAL_MODULE" "$@"
