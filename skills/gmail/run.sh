#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/agent-skills-gmail-uv-env}"
if command -v uv >/dev/null 2>&1; then
  exec uv run --project "$SCRIPT_DIR" python -m gmail_skill.cli "$@"
fi
exec python3 -m gmail_skill.cli "$@"
