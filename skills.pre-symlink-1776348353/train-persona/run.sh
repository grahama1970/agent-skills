#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
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

usage() {
    cat << EOF
train-persona: Train LoRA adapters for persona agents

Usage: ./run.sh <command> [options]

Data Generation:
  generate          Generate training conversations from persona definition
  upgrade-traces    Apply multi-role critique to improve reasoning traces
  extract-episodes  Extract correction episodes from upgraded traces

Training:
  train             Run λ-GRPO training for persona
  warmup            SFT warmup before GRPO
  merge             Merge LoRA into base model

Evaluation:
  evaluate          Run persona evaluation suite
  chat              Interactive chat with trained persona
  compare           Compare persona versions

Options:
  --persona NAME        Persona name (required for most commands)
  --grpo-steps N        Number of GRPO training steps (default: 2000)
  --lambda-grpo         Use λ-GRPO normalization (recommended)
  --conversations N     Number of conversations to generate (default: 1000)
  --samples N           Number of evaluation samples (default: 50)
  --source SOURCE       Data source: create-persona, episodic-archiver, manual
  --reality-check       Use /reality-check-sparta for grounding validation

Examples:
  ./run.sh generate --persona Embry --conversations 1000
  ./run.sh upgrade-traces --persona Embry
  ./run.sh train --persona Embry --grpo-steps 2000 --lambda-grpo
  ./run.sh evaluate --persona Embry --reality-check
  ./run.sh chat --persona Embry
EOF
}

# Default values
PERSONA=""
GRPO_STEPS=2000
LAMBDA_GRPO=false
CONVERSATIONS=1000
SAMPLES=50
SOURCE="create-persona"
REALITY_CHECK=false

COMMAND="${1:-}"
shift || true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --persona)
            PERSONA="$2"
            shift 2
            ;;
        --grpo-steps)
            GRPO_STEPS="$2"
            shift 2
            ;;
        --lambda-grpo)
            LAMBDA_GRPO=true
            shift
            ;;
        --conversations)
            CONVERSATIONS="$2"
            shift 2
            ;;
        --samples)
            SAMPLES="$2"
            shift 2
            ;;
        --source)
            SOURCE="$2"
            shift 2
            ;;
        --reality-check)
            REALITY_CHECK=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

case "$COMMAND" in
    generate)
        if [[ -z "$PERSONA" ]]; then
            echo "ERROR: --persona required" >&2
            exit 1
        fi
        echo "Generating $CONVERSATIONS conversations for persona: $PERSONA"
        echo "Source: $SOURCE"
        cd "$SCRIPT_DIR"
        exec uv run python scripts/generate.py \
            --persona "$PERSONA" \
            --source "$SOURCE" \
            --conversations "$CONVERSATIONS" \
            --output "data/${PERSONA,,}/conversations.jsonl"
        ;;
    upgrade-traces)
        if [[ -z "$PERSONA" ]]; then
            echo "ERROR: --persona required" >&2
            exit 1
        fi
        echo "Upgrading reasoning traces for persona: $PERSONA"
        cd "$SCRIPT_DIR"
        exec uv run python scripts/upgrade_traces.py \
            --input "data/${PERSONA,,}/conversations.jsonl" \
            --output "data/${PERSONA,,}/upgraded.jsonl" \
            --episodes-output "data/${PERSONA,,}/episodes.jsonl"
        ;;
    extract-episodes)
        if [[ -z "$PERSONA" ]]; then
            echo "ERROR: --persona required" >&2
            exit 1
        fi
        echo "Extracting correction episodes for persona: $PERSONA"
        cd "$SCRIPT_DIR"
        exec uv run python scripts/extract_episodes.py \
            --input "data/${PERSONA,,}/upgraded.jsonl" \
            --output "data/${PERSONA,,}/episodes.jsonl"
        ;;
    train)
        if [[ -z "$PERSONA" ]]; then
            echo "ERROR: --persona required" >&2
            exit 1
        fi
        echo "Training persona: $PERSONA with $GRPO_STEPS GRPO steps"
        LAMBDA_FLAG=""
        if [[ "$LAMBDA_GRPO" == "true" ]]; then
            echo "Using λ-GRPO normalization"
            LAMBDA_FLAG="--lambda-grpo"
        fi
        cd "$SCRIPT_DIR"
        exec uv run python scripts/train_persona.py \
            --persona "$PERSONA" \
            --train-file "data/${PERSONA,,}/upgraded.jsonl" \
            --grpo-steps "$GRPO_STEPS" \
            --output "models/${PERSONA,,}-v1" \
            $LAMBDA_FLAG
        ;;
    warmup)
        if [[ -z "$PERSONA" ]]; then
            echo "ERROR: --persona required" >&2
            exit 1
        fi
        echo "SFT warmup for persona: $PERSONA"
        cd "$SCRIPT_DIR"
        exec uv run python scripts/train_persona.py \
            --persona "$PERSONA" \
            --train-file "data/${PERSONA,,}/upgraded.jsonl" \
            --warmup-only \
            --output "models/${PERSONA,,}-warmup"
        ;;
    merge)
        if [[ -z "$PERSONA" ]]; then
            echo "ERROR: --persona required" >&2
            exit 1
        fi
        echo "Merging LoRA for persona: $PERSONA"
        cd "$SCRIPT_DIR"
        exec uv run python scripts/merge_lora.py \
            --adapter "models/${PERSONA,,}-v1" \
            --output "models/${PERSONA,,}-merged"
        ;;
    evaluate)
        if [[ -z "$PERSONA" ]]; then
            echo "ERROR: --persona required" >&2
            exit 1
        fi
        echo "Evaluating persona: $PERSONA with $SAMPLES samples"
        REALITY_FLAG=""
        if [[ "$REALITY_CHECK" == "true" ]]; then
            echo "Using /reality-check-sparta for grounding validation"
            REALITY_FLAG="--reality-check"
        fi
        cd "$SCRIPT_DIR"
        exec uv run python scripts/evaluate_persona.py \
            --persona "$PERSONA" \
            --model "models/${PERSONA,,}-v1" \
            --samples "$SAMPLES" \
            $REALITY_FLAG
        ;;
    chat)
        if [[ -z "$PERSONA" ]]; then
            echo "ERROR: --persona required" >&2
            exit 1
        fi
        echo "Interactive chat with persona: $PERSONA"
        cd "$SCRIPT_DIR"
        exec uv run python scripts/chat.py \
            --persona "$PERSONA" \
            --model "models/${PERSONA,,}-v1"
        ;;
    compare)
        if [[ -z "$PERSONA" ]]; then
            echo "ERROR: --persona required" >&2
            exit 1
        fi
        echo "Comparing persona versions: $PERSONA"
        cd "$SCRIPT_DIR"
        exec uv run python scripts/compare_versions.py \
            --persona "$PERSONA"
        ;;
    "")
        usage
        exit 1
        ;;
    *)
        echo "Unknown command: $COMMAND" >&2
        usage
        exit 1
        ;;
esac
