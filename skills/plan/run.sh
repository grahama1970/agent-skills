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

ARTIFACT_ROOT="${PLAN_ARTIFACT_ROOT:-/mnt/storage12tb/skills/plan}"
export UV_PROJECT_ENVIRONMENT="${PLAN_UV_ENV:-$ARTIFACT_ROOT/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
export PYTHONDONTWRITEBYTECODE=1

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
UV_PROJECT_ENVIRONMENT="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve(strict=False))' "$UV_PROJECT_ENVIRONMENT")"
export UV_PROJECT_ENVIRONMENT
case "$UV_PROJECT_ENVIRONMENT" in
    "$PROJECT_ROOT"/*)
        if [ "${PLAN_ALLOW_UNSAFE_ARTIFACT_ROOT:-0}" != "1" ]; then
            echo "Error: PLAN_UV_ENV points inside the repository: $UV_PROJECT_ENVIRONMENT" >&2
            echo "Use /mnt/storage12tb or set PLAN_ALLOW_UNSAFE_ARTIFACT_ROOT=1 for an explicit unsafe override." >&2
            exit 2
        fi
        ;;
esac
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"

# Use uv if available, otherwise python3
if command -v uv &> /dev/null; then
    EXEC=(uv run --project "$SCRIPT_DIR" python)
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
