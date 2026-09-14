#!/usr/bin/env bash
unset VIRTUAL_ENV
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/scripts/watchdog_v2.py" "$@"
