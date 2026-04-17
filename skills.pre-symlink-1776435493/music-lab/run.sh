#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
#
# music-lab Skill Runner
# Self-improving music creation convergence loop
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
Usage: ./run.sh <command> [options]

Commands:
  pipeline  PROJECT [--topic TOPIC] [--out DIR] [--dry-run]
            Run the full lore-to-audio creation pipeline (S00-S07)
  converge  --spec FILE --lyrics FILE --out DIR [--backend yue|sonauto] [--max-rounds N] [--dry-run]
            Run the audio convergence loop only (S06)
  status    PROJECT   Show pipeline/convergence status
  nightly   Nightly wrapper for scheduler
  sanity    Run sanity checks

Options:
  --help    Show this help message
EOF
}

COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
    pipeline)
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/pipeline.py" run "$@"
        ;;
    converge)
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/converge.py" converge "$@"
        ;;
    status)
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/pipeline.py" status "$@"
        ;;
    nightly)
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/converge.py" nightly "$@"
        ;;
    sanity)
        exec bash "${SCRIPT_DIR}/sanity.sh" "$@"
        ;;
    help|--help|-h)
        usage
        exit 0
        ;;
    *)
        echo "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
