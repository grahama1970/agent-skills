#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts
unset VIRTUAL_ENV
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-help}" in
  compose)
    shift
    exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/compose.py" "$@"
    ;;
  from-spec)
    shift
    exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/midi_utils.py" from-spec "$@"
    ;;
  to-spec)
    shift
    exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/midi_utils.py" to-spec "$@"
    ;;
  validate-score-packet)
    shift
    exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/battle_score_packet.py" validate "$@"
    ;;
  help|--help|-h)
    echo "Usage: ./run.sh <command>"
    echo "  compose    --lyrics FILE --references FILE --heart TAGS --out FILE"
    echo "  from-spec  --spec FILE --out FILE"
    echo "  to-spec    --midi FILE --out FILE"
    echo "  validate-score-packet --packet FILE [--motif-manifest FILE] [--out FILE]"
    ;;
  *)
    echo "Unknown: $1"; exit 1 ;;
esac
