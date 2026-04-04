#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure venv exists
if [ ! -d "$SKILL_DIR/.venv" ]; then
    echo "Installing dependencies..."
    (cd "$SKILL_DIR" && uv sync --quiet 2>/dev/null || uv pip install -e . --quiet)
fi

# Load environment
COMMON_SH="$(dirname "$SKILL_DIR")/common/common.sh"
if [ -f "$COMMON_SH" ]; then
    # shellcheck disable=SC1090
    source "$COMMON_SH"
fi

exec uv run --project "$SKILL_DIR" python "$SKILL_DIR/test_runner.py" "$@"
