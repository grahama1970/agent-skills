#!/usr/bin/env bash
unset VIRTUAL_ENV
# ops-obs: monitor and optimize OBS Studio (obs-websocket v5 + local diagnostics).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "${1:-}" = "verify" ]; then
  shift
  exec "$SCRIPT_DIR/../agentic-evals/run.sh" run "$SCRIPT_DIR/fixtures/agentic_eval.json" "$@"
fi

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/ops_obs.py" "$@"
