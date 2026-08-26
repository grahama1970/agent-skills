#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Agentic eval passthrough: ./run.sh eval  -> multi-trial behavior gates
if [ "${1:-}" = "eval" ]; then
  shift
  exec "${HOME}/.claude/skills/agentic-evals/run.sh" run "${SCRIPT_DIR}/fixtures/agentic_eval.json" "$@"
fi

if [ "${1:-}" = "website-gate" ]; then
  shift
  exec "${SCRIPT_DIR}/../monitor-website/run.sh" interaction-check \
    --url "https://grahama.co/" \
    --resume-url "https://grahama.co/resume" \
    "$@"
fi


# Local untracked environment (e.g. BUZZ_IDENTITY_KEY) for cron runs whose
# daemon env is empty; safe no-op when absent.
if [ -f "${SCRIPT_DIR}/local/env" ]; then
  # shellcheck disable=SC1091
  . "${SCRIPT_DIR}/local/env"
fi
exec uv run --project "$SCRIPT_DIR" monitor-opportunities "$@"
