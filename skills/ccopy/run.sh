#!/usr/bin/env bash
# ccopy skill runner
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${ROOT}/scripts${PYTHONPATH:+:$PYTHONPATH}"

cmd="${1:-help}"
shift || true

case "$cmd" in
  copy)
    exec python3 "${ROOT}/scripts/cursor_copy.py" "$@"
    ;;
  diagnose)
    exec python3 "${ROOT}/scripts/cursor_copy.py" --diagnose "$@"
    ;;
  test)
    exec python3 -m unittest discover -s "${ROOT}/tests" -v "$@"
    ;;
  sanity)
    exec "${ROOT}/sanity.sh" "$@"
    ;;
  help|--help|-h)
    cat <<EOF
Usage: ./run.sh <command> [args]

Commands:
  copy       Run ccopy (passes args to cursor_copy.py)
  diagnose   Print storage diagnostics for cwd
  test       Run unit tests
  sanity     Run behavioral sanity gates
  help       Show this message
EOF
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    exit 2
    ;;
esac
