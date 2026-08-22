#!/usr/bin/env bash
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --quiet --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/diagnose.py" "$@"
