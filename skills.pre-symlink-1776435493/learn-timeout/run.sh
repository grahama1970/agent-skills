#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Learn Timeout - General-Purpose Timeout Estimation
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
cd "$SCRIPT_DIR"

# Create venv if needed
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv .venv
    source .venv/bin/activate
    uv pip install -e .
else
    source .venv/bin/activate
fi

# Route commands
case "${1:-help}" in
    collect)
        shift
        python scripts/collect.py "$@"
        ;;
    train)
        shift
        python scripts/train.py "$@"
        ;;
    predict)
        shift
        python scripts/predict.py "$@"
        ;;
    observe)
        shift
        python scripts/observe.py "$@"
        ;;
    status)
        shift
        python scripts/status.py "$@"
        ;;
    benchmark)
        shift
        python scripts/train.py --classifier-lab-benchmark "$@"
        ;;
    *)
        echo "Learn Timeout - General-Purpose Timeout Estimation"
        echo ""
        echo "Commands:"
        echo "  collect     Gather training data from all sources"
        echo "  train       Train duration + risk models"
        echo "  predict     Predict timeout from JSON features"
        echo "  observe     Record actual outcome for feedback loop"
        echo "  status      Model health dashboard"
        echo "  benchmark   Run classifier-lab backbone comparison"
        echo ""
        echo "Examples:"
        echo "  ./run.sh collect"
        echo "  ./run.sh train"
        echo "  ./run.sh predict '{\"task_type\":\"pdf_extraction\",\"page_count\":400}'"
        echo "  ./run.sh observe --task-id abc123 --actual-seconds 4200"
        echo "  ./run.sh status"
        ;;
esac
