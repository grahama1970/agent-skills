#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Plan skill runner
# Creates orchestration-ready task files with enforced quality gates

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

# Use uv if available, otherwise python3
if command -v uv &> /dev/null; then
    EXEC=(uv run python)
else
    EXEC=(python3)
fi

# Show help if no arguments
if [ $# -eq 0 ]; then
    cat << 'EOF'
Plan Skill - Create orchestration-ready task files

Usage:
  plan.sh "goal description"       # Start planning session
  plan.sh --validate FILE          # Validate existing plan file
  plan.sh --dag FILE               # Visualize execution DAG
  plan.sh --mermaid FILE           # DAG as Mermaid flowchart
  plan.sh --add-task FILE "fields" # Add task to existing plan
  plan.sh --remove-task FILE:ID    # Remove task from plan

Examples:
  plan.sh "Add Redis caching to API"
  plan.sh --validate 01_TASKS.yaml
  plan.sh --dag 01_TASKS.yaml

Output: A compliant 0N_TASKS.yaml file ready for /orchestrate
EOF
    exit 0
fi

# Handle --validate flag
if [ "$1" == "--validate" ]; then
    if [ -z "$2" ]; then
        echo "Error: --validate requires a file path"
        exit 1
    fi
    "${EXEC[@]}" "$SCRIPT_DIR/plan.py" --validate "$2"
    exit $?
fi


# Default: run planning with goal
"${EXEC[@]}" "$SCRIPT_DIR/plan.py" "$@"
