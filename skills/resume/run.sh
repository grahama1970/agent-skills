#!/usr/bin/env bash
set -euo pipefail

unset VIRTUAL_ENV
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv is required to run the resume skill" >&2
    exit 1
fi

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/resume.py" "$@"
