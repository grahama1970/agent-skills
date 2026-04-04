#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Classifier Lab - General Vision Classifier Training
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
    uv pip install torch torchvision timm loguru typer tqdm pillow transformers scikit-learn numpy tensorboard tbparse
else
    source .venv/bin/activate
fi

# Route commands
case "${1:-help}" in
    train)
        shift
        python scripts/train.py train "$@"
        ;;
    evaluate)
        shift
        python scripts/train.py evaluate "$@"
        ;;
    benchmark)
        shift
        python scripts/benchmark.py "$@"
        ;;
    text-benchmark)
        shift
        python scripts/benchmark.py benchmark --modality text "$@"
        ;;
    tabular-benchmark)
        shift
        python scripts/benchmark.py benchmark --modality tabular "$@"
        ;;
    tb-summary)
        shift
        python scripts/tb_summary.py tb "$@"
        ;;
    status)
        shift
        python scripts/tb_summary.py status "$@"
        ;;
    export)
        shift
        python scripts/export.py "$@"
        ;;
    ensemble)
        shift
        python scripts/ensemble.py "$@"
        ;;
    e2e)
        shift
        python scripts/e2e_pipeline.py "$@"
        ;;
    concurrent-run)
        shift
        python scripts/concurrent_run.py run "$@"
        ;;
    concurrent-manifests)
        shift
        python scripts/concurrent_run.py manifests "$@"
        ;;
    gui|app)
        shift
        python app.py "$@"
        ;;
    *)
        echo "Classifier Lab - Multi-Modality Classifier Training"
        echo ""
        echo "Commands:"
        echo "  train             Train a classifier on your dataset"
        echo "  evaluate          Evaluate a trained model"
        echo "  benchmark         Compare multiple backbones (vision/text/tabular)"
        echo "  text-benchmark    Shorthand for benchmark --modality text"
        echo "  tabular-benchmark Shorthand for benchmark --modality tabular"
        echo "  tb-summary        Read TensorBoard events and show training progress"
        echo "  status            Show active/completed benchmark runs (MUST CHECK)"
        echo "  ensemble          Create ensemble from multiple models"
        echo "  export            Export model to ONNX/TorchScript"
        echo "  concurrent-run    Race multiple backbones via Switchboard (concurrent)"
        echo "  concurrent-manifests  Generate Switchboard manifests only (dry run)"
        echo "  gui|app           Launch the PySide6/QML GUI"
        echo ""
        echo "Train flags:"
        echo "  --target local    Train locally (default)"
        echo "  --target flash    Submit to RunPod Flash cloud GPU (requires RUNPOD_API_KEY)"
        echo ""
        echo "Examples:"
        echo "  ./run.sh train --data-dir data/images --backbone efficientnet_b0"
        echo "  ./run.sh train --data-dir data/images --backbone efficientnet_b0 --target flash"
        echo "  ./run.sh benchmark --data-dir data/images --backbones 'efficientnet_b0,convnextv2_nano'"
        echo "  ./run.sh text-benchmark --labels-jsonl data/text.jsonl --backbones 'prajjwal1/bert-tiny,distilbert-base-uncased'"
        echo "  ./run.sh tabular-benchmark --labels-jsonl data/features.jsonl --backbones 'gradient_boosting,random_forest'"
        echo "  ./run.sh ensemble --models 'model1,model2' --weights '0.6,0.4'"
        ;;
esac
