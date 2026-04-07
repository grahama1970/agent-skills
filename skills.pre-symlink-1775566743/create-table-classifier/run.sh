#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Table Strategy Classifier - CLI Wrapper
#
# Usage:
#   ./run.sh collect --corpus /path/to/pdfs --limit 5000
#   ./run.sh warmup --train-file data/labels/train.jsonl
#   ./run.sh grpo --checkpoint models/table-classifier-sft
#   ./run.sh train-full --train-file data/labels/train.jsonl
#   ./run.sh evaluate --model models/table-classifier-grpo
#   ./run.sh infer --image data/images/test/sample.png

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

cd "$SCRIPT_DIR"

# Load environment
if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

# Ensure uv is available
if ! command -v uv &> /dev/null; then
    echo "uv not found. Please install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Initialize venv if needed
if [[ ! -d .venv ]]; then
    echo "Creating virtual environment..."
    uv venv .venv
    uv pip install -e .
fi

CMD="${1:-help}"
shift || true

case "$CMD" in
    collect)
        echo "Collecting training data from corpus..."
        uv run python scripts/collect_training_data.py "$@"
        ;;

    split)
        echo "Splitting data into train/eval..."
        uv run python scripts/evaluate.py split "$@"
        ;;

    stats)
        echo "Dataset statistics..."
        uv run python scripts/evaluate.py stats "$@"
        ;;

    warmup)
        echo "Running SFT warmup..."
        uv run python scripts/train_sft.py "$@"
        ;;

    grpo)
        echo "Running GRPO training with Camelot feedback..."
        uv run python scripts/train_grpo.py grpo "$@"
        ;;

    train-full)
        echo "Running full training pipeline..."
        uv run python scripts/train_grpo.py train "$@"
        ;;

    evaluate)
        echo "Running evaluation..."
        uv run python scripts/evaluate.py run "$@"
        ;;

    infer)
        echo "Running inference..."
        uv run python scripts/inference.py "$@"
        ;;

    export)
        echo "Exporting model for S05..."
        uv run python scripts/inference.py export "$@"
        ;;

    tensorboard)
        echo "Starting TensorBoard..."
        uv run tensorboard --logdir logs "$@"
        ;;

    logs)
        tail -f logs/training.log 2>/dev/null || echo "No training logs found"
        ;;

    self-improve)
        echo "Running self-improvement cycle..."
        uv run python scripts/self_improve.py "$@"
        ;;

    shell)
        echo "Starting interactive shell..."
        uv run python
        ;;

    help|--help|-h)
        cat << 'EOF'
Table Strategy Classifier - Train models to predict Camelot extraction strategies

Commands:
  collect       Collect training data from S05 outputs
  split         Split data into train/eval sets
  stats         Show dataset statistics
  warmup        Run SFT warmup training
  grpo          Run GRPO training with Camelot feedback
  train-full    Full pipeline: warmup -> GRPO -> eval
  evaluate      Run evaluation on holdout set
  infer         Test inference on image
  export        Export model for S05 integration
  tensorboard   Start TensorBoard server
  logs          Tail training logs
  self-improve  Run full self-improvement cycle
  shell         Interactive Python shell

Examples:
  ./run.sh collect --corpus /path/to/pdfs --limit 5000
  ./run.sh train-full --train-file data/labels/train.jsonl --wandb
  ./run.sh infer --image data/images/test/table.png

Environment:
  EXTRACTOR_PATH     Path to extractor project (for Camelot)
  MEMORY_BASE_URL    /memory API URL for Federated Taxonomy
  WANDB_API_KEY      Weights & Biases API key (optional)
  CUDA_VISIBLE_DEVICES  GPU selection

See SKILL.md for full documentation.
EOF
        ;;

    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
