#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Regressor Lab — iterative regression benchmarking and development
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
REGRESSOR_SKILL="$(dirname "$SKILL_DIR")/create-regressor"
cd "$SKILL_DIR"

CMD="${1:-help}"
shift || true

case "$CMD" in
  benchmark)
    uv run python scripts/benchmark.py "$@"
    ;;
  tune)
    uv run python scripts/tune.py "$@"
    ;;
  rationale)
    uv run python scripts/rationale.py "$@"
    ;;
  evaluate)
    uv run python scripts/evaluate.py "$@"
    ;;
  compare)
    uv run python scripts/compare.py "$@"
    ;;
  collect)
    uv run python scripts/collect.py "$@"
    ;;
  pipeline)
    uv run python scripts/pipeline.py "$@"
    ;;
  deploy)
    uv run python scripts/deploy.py "$@"
    ;;
  gui|app)
    uv run --extra gui python app.py "$@"
    ;;
  sanity)
    bash sanity.sh
    ;;
  help|--help|-h)
    echo "Regressor Lab — Iterative Regression Model Benchmarking"
    echo ""
    echo "Commands:"
    echo "  benchmark   Compare architectures:  ./run.sh benchmark data.jsonl --target col --name mymodel"
    echo "  tune        HP search on winner:    ./run.sh tune mymodel --trials 50"
    echo "  rationale   Train rationale GPT:    ./run.sh rationale mymodel --train-gpt"
    echo "  evaluate    Holdout evaluation:     ./run.sh evaluate mymodel --test holdout.jsonl"
    echo "  compare     Head-to-head:           ./run.sh compare model-a model-b --test holdout.jsonl"
    echo "  collect     Gather training data:   ./run.sh collect --source profiles --out data/timeout.jsonl"
    echo "  pipeline    Full end-to-end:        ./run.sh pipeline data.jsonl --target col --name mymodel"
    echo "  deploy      Wire into target:       ./run.sh deploy mymodel --target-file path/to/discovery.py"
    echo "  gui|app     Launch QML desktop app:  ./run.sh gui"
    echo "  sanity      Run sanity checks:      ./run.sh sanity"
    echo ""
    echo "Models: linear, ridge, lasso, elasticnet, gbr, rf, xgb, auto (default: all)"
    ;;
  *)
    echo "Unknown command: $CMD" >&2
    echo "Run ./run.sh help for usage." >&2
    exit 1
    ;;
esac
