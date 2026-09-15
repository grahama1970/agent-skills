#!/usr/bin/env bash
unset VIRTUAL_ENV
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == "workflow" ]]; then
  shift
  exec python3 "$SCRIPT_DIR/scripts/watchdog_workflow_cli.py" "$@"
fi
exec python3 "$SCRIPT_DIR/scripts/watchdog_v2.py" "$@"
