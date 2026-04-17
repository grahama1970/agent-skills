#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# review-design skill entry point
#
# Usage:
#   ./run.sh review --screenshots ./ui/ --tokens ./tokens.json
#   ./run.sh review --screenshots ./current/ --reference ./raycast/ --rounds 2
#   ./run.sh check --provider claude
#   ./run.sh bundle --screenshots ./ui/ --output review.md

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

# Ensure we're in the skill directory
cd "$SCRIPT_DIR"

# Use venv if available (has google-generativeai)
if [[ -f "$SCRIPT_DIR/.venv/bin/python" ]]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON="python3"
else
    echo "Error: python3 not found" >&2
    exit 1
fi

# Run the orchestrator
exec "$PYTHON" review_design.py "$@"
