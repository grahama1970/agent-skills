#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'USAGE'
voice-segment-selector

Usage:
  ./run.sh prepare --input PATH [--job-dir DIR] [--chapters-json PATH] [--classifier both|hf|f0]
  ./run.sh review  --job-dir DIR [--port 8791]
  ./run.sh decide   --job-dir DIR --id 0001 --decision accept|reject|maybe
  ./run.sh export  --job-dir DIR [--out-dir DIR] [--gender male|female] [--auto-accept-top N]
  ./run.sh bundle  --job-dir DIR --gender male|female [--target-sec 30]

Defaults:
  job-dir     /tmp/voice-segment-selector-<timestamp>
  clip length 6-18 seconds
  classifier  both (Norwood HF with F0 fallback)

Examples:
  ./run.sh prepare --input interview.mp4
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
  prepare|review|decide|export|bundle)
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
