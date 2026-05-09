#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SKILL_DIR"

# Accept the documented `./run.sh review ...` shape while preserving the
# existing single-command Typer entrypoint.
if [[ "${1:-}" == "review" ]]; then
  shift
fi

uv run python review_prompt.py "$@"
