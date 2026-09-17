#!/usr/bin/env bash
# Jev skill entrypoint. Usage: ./run.sh <command> [args...]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --project "$SCRIPT_DIR" --quiet python "$SCRIPT_DIR/scripts/jev.py" "$@"
