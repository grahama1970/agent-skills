#!/bin/bash
# Plan skill runner
# Creates orchestration-ready task files with enforced quality gates

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
  plan.sh --validate FILE          # Validate existing task file
  plan.sh --analyze-deps "text"    # Find non-standard dependencies

Examples:
  plan.sh "Add Redis caching to API"
  plan.sh --validate 01_TASKS.md
  plan.sh --analyze-deps "use camelot and pdfplumber"

The skill guides you through:
1. Requirement gathering (clarifying questions)
2. Dependency research (sanity scripts for non-standard APIs)
3. Task breakdown (with parallel grouping)
4. Test definition (Definition of Done for each task)
5. Validation (preflight check before orchestration)

Output: A compliant 0N_TASKS.md file ready for /orchestrate
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

# Handle --analyze-deps flag
if [ "$1" == "--analyze-deps" ]; then
    if [ -z "$2" ]; then
        echo "Error: --analyze-deps requires text to analyze"
        exit 1
    fi
    "${EXEC[@]}" "$SCRIPT_DIR/plan.py" --analyze-deps "$2"
    exit $?
fi

# Default: run planning with goal
"${EXEC[@]}" "$SCRIPT_DIR/plan.py" "$@"
