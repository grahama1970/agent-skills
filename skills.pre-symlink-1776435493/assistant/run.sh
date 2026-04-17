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

show_usage() {
    cat <<'EOF'
Usage: run.sh <command> [args]

Commands:
  validate    Validate input through 4-tier cascade (heuristic → classifier → GPT → scillm)
  classify    Classify text through 3-tier cascade (heuristic → classifier → scillm)
  register    Register a new model in the registry
  status      Show registered models, hit rates, tier distribution
  self-test   Run synthetic input through all tiers
  harvest     Extract tier-2 escalations as training data
  train       Train Tier 0.5 sklearn classifiers from harvested labels
  prime       Prime shadow entries via scillm teacher labels

Examples:
  ./run.sh validate --task qra-assessor --scope brandon_bailey --input '{"question":"...", "answer":"..."}'
  ./run.sh classify --task bridge-tagger --text "satellite vulnerability assessment"
  ./run.sh register --task my-task --model-path /path/to/model.gguf --type gpt --threshold 0.85
  ./run.sh status
  ./run.sh self-test
  ./run.sh harvest --since 24h
EOF
}

# Check for uv
if command -v uv &> /dev/null; then
    EXEC=(uv run --project "$SCRIPT_DIR" python)
else
    EXEC=(python3)
fi

main() {
    if [[ $# -eq 0 ]]; then
        show_usage
        exit 1
    fi

    local command="$1"
    shift

    case "$command" in
        validate|classify|register|status|self-test)
            "${EXEC[@]}" "$SCRIPT_DIR/assistant.py" "$command" "$@"
            ;;
        harvest)
            "${EXEC[@]}" "$SCRIPT_DIR/harvest.py" "$@"
            ;;
        train)
            "${EXEC[@]}" "$SCRIPT_DIR/train_classifiers.py" "$@"
            ;;
        prime)
            "${EXEC[@]}" "$SCRIPT_DIR/prime_shadow.py" "$@"
            ;;
        help|--help|-h)
            show_usage
            ;;
        *)
            echo "Error: Unknown command: $command" >&2
            echo "" >&2
            show_usage >&2
            exit 1
            ;;
    esac
}

main "$@"
