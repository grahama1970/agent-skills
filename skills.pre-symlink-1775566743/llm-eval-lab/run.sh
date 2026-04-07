#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# LLM Eval Lab: Model evaluation, comparison, and cost analysis
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

cd "$SCRIPT_DIR"

# Load environment from sparta (for API keys etc)
SPARTA_ENV="/home/graham/workspace/experiments/sparta/.env"
if [ -f "$SPARTA_ENV" ]; then
    set -a
    source "$SPARTA_ENV"
    set +a
fi

# Also load local .env if it exists
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Run with uv (handles venv automatically via pyproject.toml)
exec uv run python llm_eval_lab.py "$@"
