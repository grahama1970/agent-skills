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

# Install deps if pyproject.toml exists
if [[ -f pyproject.toml ]]; then
    uv pip install -e . 2>/dev/null || true
fi

# Run the main Python script
source .venv/bin/activate
python perplexity.py "$@"
