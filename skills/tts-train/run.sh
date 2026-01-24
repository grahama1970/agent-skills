#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

usage() {
  cat <<'USAGE'
Usage: run.sh <command> [args]

Commands:
  ingest <audio> <book_name> <output_dir>    Ingest a single audio file (project env)
  ingest-transcript <input_dir> <jsonl> <output_dir>  Build dataset from clips + transcript JSONL (project env)
  align <manifest> <output> <dataset_root>   WhisperX alignment (project env)
  sanity <config> [steps]                     Quick sanity check before long training (skill env)
  train-local <config>                        Train XTTS locally (skill env)
  train-runpod <config>                       Launch RunPod training (stub)
  infer <config> <output_wav>                 Synthesize a sample using trained XTTS (skill env)
  tensorboard [port]                          Start TensorBoard (skill env)
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
  sanity)
    config="${2:-}"
    steps="${3:-50}"
    [[ -z "$config" ]] && usage && exit 1
    echo "Running sanity check ($steps steps) before long training..."
    (cd "$SCRIPT_DIR" && COQUI_TOS_AGREED=1 UV_PYTHON=3.10 uv run python "$ROOT_DIR/run/tts/quick_sanity_check.py" \
      --config "$config" --steps "$steps")
    ;;
  train-local)
    config="${2:-}"
    [[ -z "$config" ]] && usage && exit 1
    (cd "$SCRIPT_DIR" && COQUI_TOS_AGREED=1 UV_PYTHON=3.10 uv run python "$ROOT_DIR/run/tts/train_xtts_coqui.py" \
      --config "$config")
    ;;
  train-runpod)
    config="${2:-}"
    [[ -z "$config" ]] && usage && exit 1
    (cd "$ROOT_DIR" && RUNPOD_GPU=1 uv run python run/tts/train_xtts.py --config "$config" --simulate False)
    ;;
  infer)
    config="${2:-}"; output="${3:-}"
    [[ -z "$config" || -z "$output" ]] && usage && exit 1
    (cd "$SCRIPT_DIR" && COQUI_TOS_AGREED=1 UV_PYTHON=3.10 uv run python "$ROOT_DIR/run/tts/xtts_infer_coqui.py" \
      --config "$config" --output "$output")
    ;;
  tensorboard)
    port="${2:-6006}"
    (cd "$SCRIPT_DIR" && uv run tensorboard --logdir "$ROOT_DIR/artifacts/tts/horus" --port "$port")
    ;;
  pipeline)
    "$ROOT_DIR/scripts/tts/run_horus_pipeline.sh"
    ;;
  *)
    usage
    exit 1
    ;;
esac
