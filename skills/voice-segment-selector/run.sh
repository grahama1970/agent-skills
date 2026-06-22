#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Torch CUDA wheels ship NVIDIA libs under site-packages; ensure the loader can find them.
if [[ -d "$SCRIPT_DIR/.venv" ]]; then
  mapfile -t _nvidia_lib_dirs < <(find "$SCRIPT_DIR/.venv" -path "*/nvidia/*/lib" -type d 2>/dev/null | sort -u)
  if ((${#_nvidia_lib_dirs[@]})); then
    _nvidia_lib_path=""
    for _dir in "${_nvidia_lib_dirs[@]}"; do
      _nvidia_lib_path="${_dir}${_nvidia_lib_path:+:${_nvidia_lib_path}}"
    done
    export LD_LIBRARY_PATH="${_nvidia_lib_path}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
  fi
fi

usage() {
  cat <<'USAGE'
voice-segment-selector

Usage:
  ./run.sh prepare (--input PATH | --inputs-file FILE) [--job-dir DIR] [--classifier both|hf|f0]
  ./run.sh prepare-aligned --input PATH [--job-dir DIR] [--speaker-id SPEAKER_00]
  ./run.sh verify --job-dir DIR [--mode auto|aligned|vad]
  ./run.sh file-maintainer-ticket --job-dir DIR [--create]
  ./run.sh analyze --job-dir DIR [--no-emotion] [--no-prosody]
  ./run.sh review  --job-dir DIR [--port 8791]
  ./run.sh decide   --job-dir DIR --id 0001 --decision accept|reject|maybe
  ./run.sh tag-propose --job-dir DIR [--gender male|female] [--no-scillm] [--limit N]
  ./run.sh export  --job-dir DIR [--out-dir DIR] [--gender male|female] [--auto-accept-top N]
  ./run.sh export-orpheus --job-dir DIR --speaker SPEAKER
  ./run.sh generate-orpheus-sfx --job-dir DIR --speaker SPEAKER [--dry-run]
  ./run.sh classify-orpheus-sfx --job-dir DIR [--no-ast]
  ./run.sh inference-smoke --speaker SPEAKER [--docker|--host-venv] [--lora-dir DIR]
  docker compose -f docker/docker-compose.orpheus-infer.yml up -d
  ./run.sh publish-orpheus --speaker SPEAKER [--repo-id ORG/NAME] [--execute]
  ./run.sh finish-orpheus --job-dir DIR --speaker SPEAKER [--publish-execute]
  ./run.sh bundle  --job-dir DIR --gender male|female [--target-sec 30]

Defaults:
  job-dir     /tmp/voice-segment-selector-<timestamp>
  clip length 6-18 seconds
  classifier  both (Norwood HF with F0 fallback)

Examples:
  ./run.sh prepare --inputs-file sources.jsonl --job-dir /tmp/voice-segment-selector-batch
  ./run.sh prepare --input interview.mp4 --input panel.mp3 --job-dir /tmp/voice-segment-selector-batch
  ./run.sh prepare --input book.m4b --chapters-json chapters.json --classifier f0 --no-transcribe
  ./run.sh review --job-dir /tmp/voice-segment-selector-20260613-120000
  ./run.sh export --job-dir /tmp/voice-segment-selector-20260613-120000 --gender female
  ./run.sh bundle --job-dir /tmp/voice-segment-selector-20260613-120000 --gender male --target-sec 30
USAGE
}

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 2
fi

cmd="${1:-}"
shift

case "$cmd" in
  prepare|prepare-aligned|analyze|tag-propose|review|decide|export|export-orpheus|generate-orpheus-sfx|classify-orpheus-sfx|inference-smoke|publish-orpheus|finish-orpheus|bundle|verify|file-maintainer-ticket)
    exec uv run --directory "$SCRIPT_DIR" python scripts/cli.py "$cmd" "$@"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
