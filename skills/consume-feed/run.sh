#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Explicitly set PYTHONPATH to the skill root to ensure module resolution works
# for `python -m cli` and internal package imports.
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"

# Use uv run to execute the module
exec uv run python -m cli "$@"
