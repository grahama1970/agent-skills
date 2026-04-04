#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Strip VIRTUAL_ENV to prevent venv conflicts
unset VIRTUAL_ENV 2>/dev/null || true

exec uv run --project "$SCRIPT_DIR" python -m scripts.thunderdome "$@"
