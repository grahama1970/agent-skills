#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export JEV_QUESTIONS_DIR="$SKILL_DIR/questions"
unset VIRTUAL_ENV
exec uv run --no-sync --project "$SKILL_DIR" python -m jev_runtime.cli "$@"
