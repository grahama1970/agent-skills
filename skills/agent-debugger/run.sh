#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "init-python" ]]; then
  shift
fi

exec python3 "$SCRIPT_DIR/scripts/create_python_debug_harness.py" "$@"
