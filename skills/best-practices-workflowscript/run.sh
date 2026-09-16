#!/usr/bin/env bash
# best-practices-workflowscript entrypoint.
# Usage: run.sh validate <file.workflow.js>   — anti-pattern lint (exit 0 clean)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD="${1:-}"
case "$CMD" in
  validate)
    [[ -n "${2:-}" ]] || { echo "usage: run.sh validate <file.workflow.js>"; exit 2; }
    exec bash "$HERE/scripts/validate-workflowscript.sh" "$2"
    ;;
  *)
    echo "usage: run.sh validate <file.workflow.js>"
    exit 2
    ;;
esac
