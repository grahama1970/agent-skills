#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# LLM Eval Lab: Model evaluation, comparison, and cost analysis
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

cd "$SCRIPT_DIR"

# Load environment from sparta (for API keys etc)
SPARTA_ENV="${HOME}/workspace/experiments/sparta/.env"
if [ -f "$SPARTA_ENV" ]; then
    set -a
    source "$SPARTA_ENV"
    set +a
fi

# Also load local .env if it exists
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# VRAM preflight: if this invocation targets a local Ollama model, refuse when
# free VRAM is below the floor so the run fails fast here instead of timing out
# inside scillm (APITimeoutError) and scoring capability as 0. Override the
# floor with LLM_EVAL_MIN_FREE_GB; local models are matched by name.
case " $* " in
  *" local-glm "*|*"local-glm,"*|*",local-glm"*|*" local-text "*|*"local-text,"*|*",local-text"*)
    if ! uv run python vram_guard.py "${LLM_EVAL_MIN_FREE_GB:-6.0}"; then
      echo "[run.sh] Aborting: VRAM guard refused a local-model run (free VRAM below floor)." >&2
      echo "[run.sh] Free VRAM (stop voice-mode/other GPU procs) or lower LLM_EVAL_MIN_FREE_GB." >&2
      exit 3
    fi
    ;;
esac

# Run with uv (handles venv automatically via pyproject.toml)
exec uv run python llm_eval_lab.py "$@"
