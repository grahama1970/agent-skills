#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure venv exists
if [[ ! -d .venv ]]; then
    uv venv .venv
    uv pip install httpx loguru tenacity
fi

case "${1:-help}" in
    match)
        shift
        uv run python match_requirement.py match "$@"
        ;;
    batch)
        shift
        uv run python match_requirement.py batch "$@"
        ;;
    coverage)
        shift
        uv run python match_requirement.py coverage "$@"
        ;;
    review-queue)
        shift
        uv run python match_requirement.py review-queue "$@"
        ;;
    help|--help|-h)
        echo "Usage: ./run.sh <command> [options]"
        echo ""
        echo "Commands:"
        echo "  match        Match a single requirement to controls"
        echo "  batch        Process batch from proof_jobs queue"
        echo "  coverage     Show matching statistics"
        echo "  review-queue List pending reviews and conflicts"
        echo ""
        echo "Examples:"
        echo "  ./run.sh match --chunk-key 'datalake_chunks/abc123'"
        echo "  ./run.sh match --chunk-key 'abc123' --confidence-threshold 0.8"
        echo "  ./run.sh batch --limit 10 --confidence-threshold 0.7"
        echo "  ./run.sh coverage --framework NIST"
        echo "  ./run.sh review-queue"
        echo "  ./run.sh review-queue --export reviews.csv"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
