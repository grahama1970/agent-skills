#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

if command -v uv >/dev/null 2>&1; then
  exec uv run --project "$SCRIPT_DIR" python -m review_paper.cli "$@"
fi

exec python3 -m review_paper.cli "$@"
