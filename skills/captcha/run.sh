#!/usr/bin/env bash
# Entry point for the authorization-gated captcha skill.
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/captcha-skill-venv}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/captcha-skill-pycache}"

if [[ "${1:-}" == "eval" ]]; then
  shift
  EVAL_RUN="${SCRIPT_DIR}/../agentic-evals/run.sh"
  if [[ ! -x "$EVAL_RUN" ]]; then
    printf 'captcha: agentic-evals run.sh is missing or not executable: %s\n' "$EVAL_RUN" >&2
    exit 2
  fi
  exec "$EVAL_RUN" run "${SCRIPT_DIR}/fixtures/agentic_eval.json" "$@"
fi

if ! command -v uv >/dev/null 2>&1; then
  printf 'captcha: uv is required for isolated skill execution\n' >&2
  exit 2
fi
exec uv run --project "$SCRIPT_DIR" python -m captcha_skill.cli "$@"
