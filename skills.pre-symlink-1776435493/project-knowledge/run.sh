#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CALLER_CWD="$(pwd)"

# Ensure venv exists (in skill dir)
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    (cd "$SCRIPT_DIR" && uv venv .venv && uv pip install -e .)
fi

# Run the CLI, passing caller's cwd as env var
export PROJECT_KNOWLEDGE_CWD="$CALLER_CWD"
exec uv run --directory "$SCRIPT_DIR" python -m project_knowledge "$@"
