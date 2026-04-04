#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# review-sparta: Brandon Bailey persona-driven SPARTA assessment
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

case "${1:-help}" in
    review)
        shift
        uv run --project "$SCRIPT_DIR" python review_sparta.py review "$@"
        ;;
    compare)
        shift
        uv run --project "$SCRIPT_DIR" python review_sparta.py compare "$@"
        ;;
    convergence)
        shift
        uv run --project "$SCRIPT_DIR" python review_sparta.py convergence "$@"
        ;;
    status)
        shift
        uv run --project "$SCRIPT_DIR" python review_sparta.py status "$@"
        ;;
    sanity)
        ./sanity.sh
        ;;
    help|--help|-h)
        echo "review-sparta: Brandon Bailey persona-driven SPARTA assessment"
        echo ""
        echo "Commands:"
        echo "  review       Run full Brandon Bailey assessment"
        echo "  compare      Compare two runs"
        echo "  convergence  Track improvement over time"
        echo "  status       Quick health check"
        echo "  sanity       Run sanity tests"
        echo ""
        echo "Examples:"
        echo "  ./run.sh review --run-id run-recovery-verify --full"
        echo "  ./run.sh review --run-id run-recovery-verify --focus qra_quality,cwe_relevance"
        echo "  ./run.sh compare run-v1 run-v2"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
