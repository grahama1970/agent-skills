#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if it exists
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

usage() {
  cat <<'USAGE'
Usage: run.sh <command> [args]

Commands:
  # Data Preparation
  prepare --input FILE --output FILE  Convert JSON to JSONL format
  variations [options]                Generate question variations with scillm
  split [options]                     Split data into train/eval sets

  # Training (Docker-based SFT)
  build                           Build Docker training image
  train [options]                 Run LoRA fine-tuning (SFT)

  # Training (GRPO with execution feedback)
  warmup [options]                SFT warmup before GRPO
  grpo [options]                  GRPO training with ArangoDB rewards
  train-full [options]            Full pipeline: warmup -> GRPO -> eval -> retry

  # Evaluation & Inference
  evaluate [options]              Run evaluation on holdout set
  infer "query"                   Test inference with trained model

  # Utilities
  merge [options]                 Merge LoRA adapter into base model
  shell                           Interactive shell in training container
  tensorboard                     Start TensorBoard for monitoring
  logs                            Tail training logs

Variation Options:
  --input FILE         Input JSONL with questions (default: data/sft/train.jsonl)
  --output FILE        Output file for variations (default: data/variations.jsonl)
  --limit N            Max questions to process (default: 2000)
  --types TYPE,...     Variation types: layperson,pm,expert,reversal (default: all)
  --concurrency N      Parallel requests to scillm (default: 4)

GRPO Options:
  --query-file FILE    Queries for GRPO training
  --eval-file FILE     Holdout evaluation data
  --steps N            GRPO training steps (default: 2000)
  --max-retries N      Max retry attempts if eval fails (default: 3)
  --wandb              Enable W&B logging (default: on)
  --mock-rewards       Use mock rewards for testing (no ArangoDB)

Examples:
  # Generate 2K question variations
  ./run.sh variations --input data/sft/train.jsonl --limit 2000

  # Full GRPO training pipeline with retry
  ./run.sh train-full --train-file data/sft/train.jsonl \
                      --query-file data/queries.txt \
                      --eval-file data/eval/test.jsonl

  # Docker-based SFT training
  ./run.sh build
  ./run.sh train --epochs 3 --batch-size 4
USAGE
}

check_env() {
  if [[ -z "${HF_TOKEN:-}" ]]; then
    echo "Error: HF_TOKEN not set. Copy .env.example to .env and add your token."
    exit 1
  fi
}

cmd="${1:-}"
shift || true

case "$cmd" in
  build)
    echo "Building Docker image..."
    docker compose build train
    ;;

  variations)
    echo "Generating question variations with scillm..."
    cd scripts
    uv run --project "$SCRIPT_DIR" python generate_variations.py generate "$@"
    ;;

  split)
    echo "Splitting data into train/eval sets..."
    cd scripts
    uv run --project "$SCRIPT_DIR" python evaluate.py split "$@"
    ;;

  warmup)
    echo "Running SFT warmup..."
    cd scripts
    uv run --project "$SCRIPT_DIR" python train_grpo.py warmup "$@"
    ;;

  grpo)
    echo "Running GRPO training with execution feedback..."
    cd scripts
    uv run --project "$SCRIPT_DIR" python train_grpo.py grpo "$@"
    ;;

  train-full)
    echo "Running full training pipeline (warmup -> GRPO -> eval -> retry)..."
    cd scripts
    uv run --project "$SCRIPT_DIR" python train_grpo.py train "$@"
    ;;

  evaluate)
    echo "Running evaluation..."
    cd scripts
    uv run --project "$SCRIPT_DIR" python evaluate.py run "$@"
    ;;

  train)
    check_env
    echo "Starting LoRA training (Docker SFT)..."
    docker compose run --rm train train "$@"
    ;;

  prepare)
    check_env
    echo "Preparing training data..."
    docker compose run --rm train prepare "$@"
    ;;

  merge)
    check_env
    echo "Merging LoRA into base model..."
    docker compose run --rm train merge "$@"
    ;;

  infer)
    check_env
    query="${1:-}"
    if [[ -z "$query" ]]; then
      echo "Error: Query required. Usage: ./run.sh infer \"your query\""
      exit 1
    fi
    shift
    echo "Running inference..."
    docker compose run --rm train infer "$query" "$@"
    ;;

  shell)
    check_env
    echo "Starting interactive shell..."
    docker compose run --rm shell
    ;;

  tensorboard)
    echo "Starting TensorBoard on http://localhost:6006..."
    docker compose up tensorboard
    ;;

  logs)
    echo "Tailing training logs..."
    tail -f logs/*.log 2>/dev/null || echo "No logs yet. Start training first."
    ;;

  help|--help|-h)
    usage
    ;;

  *)
    usage
    exit 1
    ;;
esac
