#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/agent-skills-gmail-uv-env}"

if command -v uv >/dev/null 2>&1 && [[ "${GMAIL_SANITY_NO_UV:-0}" != "1" ]]; then
  EXEC=(uv run --project "$SCRIPT_DIR" --extra dev python)
else
  EXEC=(python3)
fi

bash -n "$SCRIPT_DIR/run.sh" "$SCRIPT_DIR/sanity.sh" "$SCRIPT_DIR/sanity-live.sh"
"${EXEC[@]}" -m compileall -q "$SCRIPT_DIR/src" "$SCRIPT_DIR/tests"
"${EXEC[@]}" -m pytest -q "$SCRIPT_DIR/tests"
"${EXEC[@]}" -m gmail_skill.cli --help >/dev/null
"${EXEC[@]}" "$SCRIPT_DIR/scripts/generate_schemas.py" --check

echo "gmail sanity: PASS"
