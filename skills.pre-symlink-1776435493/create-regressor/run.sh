#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# create-regressor entry point
# Usage: ./run.sh <command> [args...]
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SKILL_DIR"

CMD="${1:-help}"
shift || true

case "$CMD" in
  train)
    uv run --extra xgboost python scripts/train.py "$@"
    ;;
  predict)
    uv run --extra xgboost python scripts/predict.py "$@"
    ;;
  evaluate)
    uv run --extra xgboost python scripts/evaluate.py "$@"
    ;;
  status)
    uv run --extra xgboost python scripts/status.py "$@"
    ;;
  importance)
    uv run --extra xgboost python scripts/importance.py "$@"
    ;;
  describe)
    uv run --extra xgboost python scripts/describe.py "$@"
    ;;
  assess)
    uv run --extra xgboost python scripts/assess_task.py "$@"
    ;;
  hp-search|tune)
    uv run --extra tuning python scripts/hp_search.py "$@"
    ;;
  iterate|train-iterative)
    uv run --extra xgboost python scripts/iterate.py "$@"
    ;;
  sanity)
    bash sanity.sh
    ;;
  help|--help|-h)
    echo "create-regressor — Train regression models from tabular data"
    echo ""
    echo "Commands:"
    echo "  train       Train a model:  ./run.sh train data.jsonl --target col --name mymodel"
    echo "  predict     Predict:        ./run.sh predict mymodel '{\"feat\": 42}'"
    echo "  evaluate    Evaluate:       ./run.sh evaluate mymodel --test test.jsonl --target col"
    echo "  status      List models:    ./run.sh status"
    echo "  importance  Feature ranks:  ./run.sh importance mymodel"
    echo "  describe    Data schema:    ./run.sh describe data.jsonl"
    echo "  assess      Preflight:      ./run.sh assess data.jsonl --target col [--dogpile-when-uncertain]"
    echo "  hp-search   HP tuning:      ./run.sh hp-search data.jsonl --target col --model gbr --trials 15"
    echo "  iterate     Self-improve:   ./run.sh iterate data.jsonl --target col --name mymodel [--run-hp-search]"
    echo "  sanity      Run sanity:     ./run.sh sanity"
    echo ""
    echo "Model types: linear, ridge, lasso, elasticnet, gbr, rf, xgb, auto"
    ;;
  *)
    echo "Unknown command: $CMD" >&2
    echo "Run ./run.sh help for usage." >&2
    exit 1
    ;;
esac
