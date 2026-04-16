#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
#
# Batch Quality Skill - Preflight validation and quality gates
#
# Usage:
#   batch-quality preflight --stage 05 --samples 3
#   batch-quality validate --stage 05 --task-name sparta-stage-05
#   batch-quality status
#   batch-quality clear
#
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
cd "$SCRIPT_DIR"

# Ensure uv is available
if ! command -v uv &>/dev/null; then
    echo "Error: uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

# Create/sync venv if needed
if [ ! -d ".venv" ]; then
    uv venv
fi

# Install dependencies
uv pip install typer 2>/dev/null || true

# Run CLI
exec uv run python cli.py "$@"
