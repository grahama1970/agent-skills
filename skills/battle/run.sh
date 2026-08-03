#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

unset VIRTUAL_ENV
export BATTLE_STORAGE_ROOT="${BATTLE_STORAGE_ROOT:-/mnt/storage12tb/skills/battle}"
mkdir -p "$BATTLE_STORAGE_ROOT"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$BATTLE_STORAGE_ROOT/.venv}"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
cd "$SCRIPT_DIR"

export PYTHONPATH="$PROJECT_ROOT/skills:$PROJECT_ROOT:$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ "${1:-}" == "prove-spectator" ]]; then
  shift
  exec "$SCRIPT_DIR/scripts/prove-spectator-local.sh" "$@"
fi

if [[ "${1:-}" == "prove-spectator-source-build" ]]; then
  shift
  exec "$SCRIPT_DIR/scripts/prove-spectator-source-build.sh" "$@"
fi

if [[ "${1:-}" == "prove-backend-goal" ]]; then
  shift
  exec "$SCRIPT_DIR/scripts/prove-backend-goal-local.sh" "$@"
fi

# Deterministic "is the backend working as expected?" eval (no live Tau/Docker/browser).
if [[ "${1:-}" == "backend-eval" ]]; then
  shift
  exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/backend_eval.py" "$@"
fi

if [[ "${1:-}" == "tiered-gate" ]]; then
  shift
  exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/tiered_qualification.py" "$@"
fi

if [[ "${1:-}" == "same-run-qualification" ]]; then
  shift
  exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/same_run_qualification.py" "$@"
fi

if [[ "${1:-}" == "current-status" ]]; then
  shift
  exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/current_status.py" "$@"
fi

if [[ "${1:-}" == "release-candidate-baseline" ]]; then
  shift
  exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/release_candidate_baseline.py" "$@"
fi

if [[ "${1:-}" == "prove-functional-evidence-status" ]]; then
  shift
  exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/prove_functional_evidence_status.py" "$@"
fi

if [[ "${1:-}" == "prove-runtime-pause-after-round" ]]; then
  shift
  exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/prove_runtime_pause_after_round.py" "$@"
fi

if [[ "${1:-}" == "human-interjection-proof" ]]; then
  shift
  exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/human_interjection_proof.py" "$@"
fi

if [[ "${1:-}" == "human-interjection-spectator-proof" ]]; then
  shift
  exec "$SCRIPT_DIR/scripts/human-interjection-spectator-proof.sh" "$@"
fi

exec uv run --project "$SCRIPT_DIR" python -m battle_skill.cli "$@"
