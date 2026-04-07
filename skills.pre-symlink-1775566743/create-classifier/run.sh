#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
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

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

CMD="${1:-help}"
shift || true

case "$CMD" in
    collect)
        python scripts/collect_labels.py "$@"
        ;;

    assess)
        python scripts/assess_task.py "$@"
        ;;
    
    train)
        python templates/vision_classifier.py "$@"
        ;;
    
    find-minimum)
        python scripts/find_minimum_model.py "$@"
        ;;
    
    tune)
        python scripts/bayesian_hyperparameter_search.py "$@"
        ;;
    
    validate)
        EXTRACTOR_VENV="../../../../extractor/.venv"
        if [ -d "$EXTRACTOR_VENV" ]; then
            echo "Using extractor venv at $EXTRACTOR_VENV"
            "$EXTRACTOR_VENV/bin/python" scripts/validate_shadow_mode.py "$@"
        else
            echo "Extractor venv not found, trying uv run..."
            uv run --project ../../../../extractor/pyproject.toml --with-requirements requirements.txt scripts/validate_shadow_mode.py "$@"
        fi
        ;;

    train-iterative)
        python scripts/iterative_train.py "$@"
        ;;

    select-model)
        python scripts/model_selector.py "$@"
        ;;

    augment)
        python scripts/hf_augment.py "$@"
        ;;
    
    evaluate)
        python scripts/evaluate.py "$@"
        ;;

    # ========================================
    # Text Classification Commands
    # ========================================

    train-text)
        python templates/text_classifier.py "$@"
        ;;

    train-text-multilabel)
        python templates/multilabel_text_classifier.py "$@"
        ;;

    select-text-model)
        python scripts/text_model_selector.py "$@"
        ;;

    train-text-iterative)
        python scripts/iterative_train_text.py "$@"
        ;;

    collect-bridge-data)
        python scripts/collect_bridge_data.py "$@"
        ;;

    bridge-inference)
        python scripts/bridge_inference.py "$@"
        ;;

    retrain-bridge)
        # Smart retraining: only retrains when sufficient new data available
        python scripts/retrain_bridge_classifier.py "$@"
        ;;

    timeout-train)
        python scripts/timeout_predictor.py train "$@"
        ;;

    timeout-infer)
        python scripts/timeout_predictor.py predict "$@"
        ;;

    mine-transcripts)
        # Mine from all CLI agents (Claude, Codex, Gemini, Pi)
        python scripts/mine_transcripts.py "$@"
        ;;

    shadow-deploy)
        echo "ERROR: shadow-deploy not yet implemented"
        echo "  This will run classifier and heuristic in parallel, log differences"
        exit 1
        ;;
    
    deploy)
        echo "ERROR: deploy not yet implemented"
        echo "  This will generate inference wrapper and copy model to target"
        exit 1
        ;;
    
    help|*)
        cat <<EOF
create-classifier - Train task-specific ML classifiers

USAGE:
    ./run.sh <command> [options]

VISION CLASSIFIER COMMANDS:
    assess              Preflight assess task/data and recommend model family
    collect             Collect training labels from pipeline outputs
    find-minimum        Find smallest model meeting accuracy threshold
    tune                Bayesian hyperparameter search with Optuna
    train               Train vision classifier (basic)
    train-iterative     Train with two-phase optimization
    select-model        Benchmark-first model selection
    augment             Conditionally augment labels from Hugging Face
    evaluate            Evaluate trained model
    shadow-deploy       Deploy in shadow mode [NOT IMPLEMENTED]
    deploy              Deploy to production [NOT IMPLEMENTED]

TEXT CLASSIFIER COMMANDS:
    train-text              Train single-label text classifier
    train-text-multilabel   Train multi-label text classifier
    select-text-model       Benchmark text backbones (latency-first)
    train-text-iterative    Full pipeline: selection + HP search + iterative training
    collect-bridge-data     Collect taxonomy bridge training data
    bridge-inference        Run inference with trained bridge classifier
    retrain-bridge          Smart retraining (checks for new data, retrains if needed)
    mine-transcripts        Mine training data from CLI agents (Claude, Codex, Gemini, Pi)
    timeout-train           Train PDF extraction timeout-risk classifier
    timeout-infer           Infer timeout risk from step00/extract features

EXAMPLES:
    # Find smallest model for document type classification
    ./run.sh find-minimum \\
        --task document_type \\
        --labels data/labels/document_type.jsonl \\
        --threshold 0.90

    # Optimize hyperparameters
    ./run.sh tune \\
        --task document_type \\
        --model efficientnet_b0 \\
        --labels data/labels/document_type.jsonl \\
        --trials 15 \\
        --output-dir models/document_type/hp_search

    # Evaluate model
    ./run.sh evaluate \\
        --model models/document_type \\
        --labels data/labels/document_type_val.jsonl

    # Benchmark-first model selection
    ./run.sh select-model \\
        --labels data/labels/document_type.jsonl \\
        --model efficientnet_b0 \\
        --candidate-backbones \
          efficientnet_b0,convnextv2_nano.fcmae_ft_in22k_in1k,resnet50 \\
        --require-classifier-lab \\
        --require-selection-pass

TEXT CLASSIFIER EXAMPLES:
    # Select fastest text model for bridge classification
    ./run.sh select-text-model \\
        --train-data data/bridge_classifier/train.jsonl \\
        --val-data data/bridge_classifier/val.jsonl \\
        --candidates prajjwal1/bert-tiny,distilbert-base-uncased \\
        --max-latency-ms 10 \\
        --accuracy-threshold 0.75

    # Full iterative training with model selection + HP search
    ./run.sh train-text-iterative \\
        --train-data data/bridge_classifier/train.jsonl \\
        --val-data data/bridge_classifier/val.jsonl \\
        --output-dir models/bridge_classifier \\
        --multilabel \\
        --run-hp-search \\
        --hp-trials 20 \\
        --accuracy-threshold 0.80 \\
        --max-latency-ms 10

    # Run bridge classifier inference
    ./run.sh bridge-inference "Evaluate the UI for accessibility" --all

    # Train timeout risk model from review-pdf aggregate reports
    ./run.sh timeout-train \\
        --reports-root /home/graham/workspace/experiments/pi-mono/.pi/skills/review-pdf/reports \\
        --output-dir models/timeout_predictor

    # Predict timeout risk for one PDF extraction context
    ./run.sh timeout-infer \\
        --page-count 120 \\
        --step00-estimated-timeout-seconds 900 \\
        --baseline-timeout-seconds 7200 \\
        --timeout-source learned

For more details, see SKILL.md
EOF
        ;;
esac
