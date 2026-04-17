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
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
echo "DEBUG ROOT_DIR: $ROOT_DIR" >&2

usage() {
  cat <<'USAGE'
Usage: run.sh <command> [args]

Commands:
  ingest <audio> <book_name> <output_dir>    Ingest a single audio file (project env)
  ingest-transcript <input_dir> <jsonl> <output_dir>  Build dataset from clips + transcript JSONL (project env)
  align <manifest> <output> <dataset_root>   WhisperX alignment (project env)
  synthesize --text <text> --output <wav>    Synthesize using Qwen3-TTS 1.7B (skill env)
  tensorboard [port]                          Start TensorBoard (skill env)
  tune-1.7b-bayesian [options]                Bayesian hyperparameter tuning for 1.7B models (skill env)
  pipeline                                   Run full Horus pipeline (background)
USAGE
}

cmd="${1:-}"
case "$cmd" in
  ingest)
    audio="${2:-}"; book="${3:-}"; out="${4:-}"
    [[ -z "$audio" || -z "$book" || -z "$out" ]] && usage && exit 1
    (cd "$ROOT_DIR" && uv run python run/tts/ingest_audiobook.py \
      --audio "$audio" --book-name "$book" --output-dir "$out" --max-hours 0)
    ;;
  ingest-transcript)
    input_dir="${2:-}"; jsonl="${3:-}"; out="${4:-}"
    [[ -z "$input_dir" || -z "$jsonl" || -z "$out" ]] && usage && exit 1
    (cd "$ROOT_DIR" && uv run python run/tts/build_dataset.py \
      --input-dir "$input_dir" --transcripts "$jsonl" --output-dir "$out")
    ;;
  align)
    manifest="${2:-}"; output="${3:-}"; root="${4:-}"
    [[ -z "$manifest" || -z "$output" || -z "$root" ]] && usage && exit 1
    (cd "$ROOT_DIR" && uv run python run/tts/align_transcripts.py \
      --manifest "$manifest" --output "$output" --dataset-root "$root" \
      --lexicon persona/docs/lexicon_overrides.json --strategy whisperx --device cuda)
    ;;
  tensorboard)
    port="${2:-6006}"
    (cd "$SCRIPT_DIR" && uv run --project "$SCRIPT_DIR" tensorboard --logdir "$ROOT_DIR/artifacts/tts/horus" --port "$port")
    ;;
  tune-1.7b-bayesian)
    shift  # Remove the command name
    echo "🎯 Starting 1.7B Bayesian hyperparameter tuning with web research..."
    echo "📊 Monitor progress: optuna-dashboard sqlite:///$ROOT_DIR/runs/horus/bayesian_tuning_1.7b/optuna_study.db"
    (cd "$SCRIPT_DIR" && uv run --project "$SCRIPT_DIR" python tune_qwen3_1.7b_bayesian_fixed.py \
      --model_size 1.7b \
      --dataset horus \
      --use_web_research \
      "$@")
    exit_code=$?
    if [ $exit_code -ne 0 ]; then
      echo "❌ Tuning failed with exit code $exit_code"
      exit $exit_code
    fi
    ;;
  synthesize)
    # Model path: env var > MEMORY_PROJECT_PATH-derived > hardcoded fallback
    MODEL_PATH="${HORUS_TTS_CHECKPOINT:-${MEMORY_PROJECT_PATH:-/home/graham/workspace/experiments/memory}/artifacts/tts/horus_qwen3_1.7b_repaired/checkpoint-epoch-9}"
    (cd "$SCRIPT_DIR" && uv run --project "$SCRIPT_DIR" python qwen3_infer_simple.py --model "$MODEL_PATH" "$@")
    ;;
  prep)
    shift
    echo "DEBUG EXEC: cd $SCRIPT_DIR && uv run --project $SCRIPT_DIR python cli.py prep $@" >&2
    (cd "$SCRIPT_DIR" && uv run --project "$SCRIPT_DIR" python cli.py prep "$@")
    ;;
  ensure-repo)
    shift
    (cd "$SCRIPT_DIR" && uv run --project "$SCRIPT_DIR" python cli.py ensure-repo "$@")
    ;;
  doctor)
    shift
    (cd "$SCRIPT_DIR" && uv run --project "$SCRIPT_DIR" python cli.py doctor "$@")
    ;;
  train-qwen3)
    shift
    (cd "$SCRIPT_DIR" && uv run --project "$SCRIPT_DIR" python cli.py train "$@")
    ;;
  synth)
    shift
    (cd "$SCRIPT_DIR" && uv run --project "$SCRIPT_DIR" python cli.py synth "$@")
    ;;
  serve)
    shift
    (cd "$SCRIPT_DIR" && uv run --project "$SCRIPT_DIR" python cli.py serve "$@")
    ;;
  pipeline)
    "$ROOT_DIR/scripts/tts/run_horus_pipeline.sh"
    ;;
  *)
    usage
    exit 1
    ;;
esac
