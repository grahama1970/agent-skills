#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# GH_TOKEN from ~/.zshrc overrides the valid keyring OAuth token, causing 401s
# with the Copilot REST API. Let the gh CLI use its keyring auth instead.
unset GH_TOKEN GITHUB_TOKEN
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/code_review.py" "$@"
