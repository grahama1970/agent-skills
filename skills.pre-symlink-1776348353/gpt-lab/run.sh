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

usage() {
  cat <<'USAGE'
Usage: run.sh <command> [args]

Commands:
  benchmark --task NAME --models "model1,model2,..."
  compare --task NAME --finetuned PATH --prompted MODEL_NAME
  find-minimum --task NAME --threshold FLOAT
  profile --model PATH --samples N
  shadow-benchmark --task NAME [--limit N] [--mock]
  report --task NAME [--format markdown|json]
  history --task NAME
  gui                                  Launch QML desktop app

Examples:
  # Benchmark multiple models
  ./run.sh benchmark --task qra-validator --models "qwen2.5-0.5b,qwen2.5-1.5b"

  # Find smallest model meeting threshold
  ./run.sh find-minimum --task qra-validator --threshold 0.85

  # Compare fine-tuned vs prompted
  ./run.sh compare --task qra-validator \
    --finetuned ../create-gpt/models/qra-validator/model.gguf \
    --prompted deepseek-v3.2

  # Profile a single model
  ./run.sh profile --model models/qra-validator/model.gguf --samples 100
USAGE
}

cmd="${1:-}"
shift || true

case "$cmd" in
  benchmark)
    echo "Running benchmark..."
    cd scripts
    uv run python benchmark.py "$@"
    ;;

  compare)
    echo "Comparing fine-tuned vs prompted..."
    cd scripts
    uv run python compare.py compare "$@"
    ;;

  find-minimum)
    echo "Finding minimum viable model..."
    cd scripts
    uv run python find_minimum.py "$@"
    ;;

  profile)
    echo "Profiling model..."
    cd scripts
    uv run python profile.py profile "$@"
    ;;

  report)
    echo "Generating report..."
    cd scripts
    uv run python report.py generate "$@"
    ;;

  shadow-benchmark)
    echo "Running shadow agreement benchmark..."
    cd scripts
    uv run python shadow_benchmark.py "$@"
    ;;

  history)
    echo "Showing benchmark history..."
    cd scripts
    uv run python report.py history "$@"
    ;;

  gui|app)
    echo "Launching GPT Lab GUI..."
    uv run python app.py
    ;;

  help|--help|-h)
    usage
    ;;

  *)
    usage
    exit 1
    ;;
esac
