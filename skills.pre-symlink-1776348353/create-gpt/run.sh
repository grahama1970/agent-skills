#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

cd "$SCRIPT_DIR"

# Load .env if it exists
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

# Warn about optional env vars needed for Tier 2 (scillm) operations
require_env_warn() {
  local var_name="$1"
  if [[ -z "${!var_name:-}" ]]; then
    echo "⚠  $var_name not set — Tier 2 (scillm) operations may fail" >&2
  fi
}
require_env_warn SCILLM_MODEL

usage() {
  cat <<'USAGE'
Usage: run.sh <command> [args]

Commands:
  # Task Definition
  define --name NAME --from-yaml FILE    Define a task from YAML spec

  # Data Preparation
  prepare --task NAME --input FILE [--augment] [--limit N]
  split --task NAME [--holdout-ratio 0.10]

  # Training
  train --task NAME [--sft-only] [--grpo-steps 2000] [--mock] [--wandb] [--target local|flash]
  train-micro --task NAME --data FILE [--layers 6] [--dim 128] [--steps 1000]

  # Self-Improvement
  hp-search --task NAME [--trials 15] [--resume]
  iterate --task NAME [--max-iterations 5] [--quality-threshold 0.85]

  # Evaluation & Export
  evaluate --task NAME [--holdout] [--mock]
  export --task NAME [--quantize Q4_K_M]

  # Teacher-Student Pipeline
  label --task NAME --input FILE [--limit N]
  loop --task NAME --input FILE [--max-rounds 3]

  # Inference
  infer "input" --task NAME [--mode gguf|hf]
  route "input" --task NAME [--threshold 0.85]
  route-batch --task NAME --input FILE [--threshold 0.85]

Examples:
  # Quick mock training cycle
  ./run.sh define --name test-task --from-yaml data/tasks/test-task.yaml
  ./run.sh prepare --task test-task --input test_data.jsonl
  ./run.sh train --task test-task --sft-only --mock
  ./run.sh evaluate --task test-task --mock

  # Full self-improvement loop
  ./run.sh hp-search --task qra-validator --trials 15
  ./run.sh iterate --task qra-validator --max-iterations 5

  # Production export and inference
  ./run.sh export --task qra-validator --quantize Q4_K_M
  ./run.sh route '{"question": "test?"}' --task qra-validator
USAGE
}

cmd="${1:-}"
shift || true

case "$cmd" in
  define)
    echo "Defining task..."
    cd scripts
    uv run python task_spec.py define "$@"
    ;;

  prepare)
    echo "Preparing training data..."
    cd scripts
    uv run python prepare_data.py prepare "$@"
    ;;

  split)
    echo "Splitting data..."
    cd scripts
    uv run python prepare_data.py split "$@"
    ;;

  train)
    echo "Training model..."
    cd scripts
    uv run python train_sft.py "$@"
    ;;

  train-micro)
    echo "Training microgpt from scratch..."
    cd scripts
    uv run python train_micro.py "$@"
    ;;

  hp-search)
    echo "Running Bayesian HP search..."
    cd scripts
    uv run python hp_search.py "$@"
    ;;

  iterate)
    echo "Running iterative self-improvement loop..."
    cd scripts
    uv run --active python iterative_train.py iterate "$@"
    ;;

  label)
    echo "Generating teacher labels..."
    cd scripts
    uv run python teacher.py "$@"
    ;;

  loop)
    echo "Running teacher-student loop..."
    cd scripts
    uv run python teacher_student_loop.py "$@"
    ;;

  evaluate)
    echo "Running evaluation..."
    cd scripts
    uv run python evaluate.py "$@"
    ;;

  export)
    echo "Exporting to GGUF..."
    cd scripts
    uv run python export_gguf.py "$@"
    ;;

  infer)
    input_text="${1:-}"
    if [[ -z "$input_text" ]]; then
      echo "Error: Input text required. Usage: ./run.sh infer \"your input\" --task NAME"
      exit 1
    fi
    shift
    cd scripts
    uv run python infer.py "$input_text" "$@"
    ;;

  route)
    input_text="${1:-}"
    if [[ -z "$input_text" ]]; then
      echo "Error: Input text required. Usage: ./run.sh route \"your input\" --task NAME"
      exit 1
    fi
    shift
    cd scripts
    uv run python router.py route "$input_text" "$@"
    ;;

  route-batch)
    echo "Batch routing..."
    cd scripts
    uv run python router.py batch "$@"
    ;;

  help|--help|-h)
    usage
    ;;

  *)
    usage
    exit 1
    ;;
esac
