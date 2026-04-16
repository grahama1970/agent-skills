#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Skill entrypoint: conversation-gradient
# Usage: ./run.sh [command] [args...]

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
PI_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Ensure we're in the project root for python execution
cd "$PI_ROOT"

# Check for uv
if command -v uv &> /dev/null; then
  EXEC=(uv run python)
else
  EXEC=(python3)
fi

# Run the Skill CLI (using -m syntax to treat the directory as a package)
# We assume the directory name in .pi/skills matches the package name "conversation-gradient"
# but the python module name is "conversation_gradient" (underscores).
# Since it's inside .pi/skills/, we need to make sure it's importable.
# The simplest usage in pi-mono is usually `python -m .pi.skills.conversation_gradient.cli` if __init__.py exists?
# OR we can just add .pi/skills to PYTHONPATH.

export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Map dash to underscore for module import
MODULE="train_convo_steering"

if [[ "$1" == *.py ]]; then
    "${EXEC[@]}" "$@"
else
    "${EXEC[@]}" -m "${MODULE}.cli" "$@"
fi
