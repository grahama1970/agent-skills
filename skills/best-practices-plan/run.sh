#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# best-practices-plan is a documentation-only skill.
# The SKILL.md IS the output — agents read it directly.
# This run.sh provides a convenience wrapper for programmatic access.

case "${1:-help}" in
    help|--help)
        echo "best-practices-plan: Conventions for orchestration-ready task files."
        echo ""
        echo "Usage:"
        echo "  ./run.sh rules     — Print all rules (for agent consumption)"
        echo "  ./run.sh check     — Check a task file against conventions"
        echo "  ./run.sh help      — This help message"
        echo ""
        echo "The SKILL.md file IS the primary reference. Agents should read it directly."
        ;;
    rules)
        cat "$SCRIPT_DIR/SKILL.md"
        ;;
    check)
        shift
        # Delegate to /review-plan which validates against these conventions
        REVIEW_PLAN="$SCRIPT_DIR/../review-plan/run.sh"
        if [ -x "$REVIEW_PLAN" ]; then
            exec "$REVIEW_PLAN" review "$@"
        else
            echo "ERROR: /review-plan skill not found. Install it first."
            exit 1
        fi
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run './run.sh help' for usage."
        exit 1
        ;;
esac
