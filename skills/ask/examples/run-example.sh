#!/usr/bin/env bash
# Persona → review-code → memory/dogpile consult → scillm agent implementation example.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASK_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ASK_DIR"

QUESTION="${1:-Brandon: review the ask DAG example module, then implement the fix with memory and dogpile when blocked}"
MODE="${2:-dry-run}"
PERSONA="${PERSONA:-Brandon}"
AGENT_WORKER="${ASK_AGENT_WORKER_ID:-implementation}"

RESOLVED="$SCRIPT_DIR/persona-review-implement.resolved.json"
uv run --project . python "$SCRIPT_DIR/build-resolved-dag.py" "$QUESTION" --persona "$PERSONA" --agent-worker "$AGENT_WORKER" -o "$RESOLVED"

if [[ "$MODE" == "dry-run" ]]; then
  exec ./run.sh ask "$QUESTION" \
    --dag-file "$RESOLVED" \
    --dry-run \
    --json \
    --ask-id "example-persona-review-implement"
fi

if [[ "$MODE" == "live" ]]; then
  echo "Live run requires: scillm on :4001, memory on :8601, implementation worker in scillm-agents.yaml" >&2
  exec ./run.sh ask "$QUESTION" \
    --dag-file "$RESOLVED" \
    --agent-worker "$AGENT_WORKER" \
    --ask-id "example-persona-review-implement" \
    --run-output-root ".ask_artifacts/examples" \
    --overwrite \
    --json
fi

echo "Usage: $0 ['question'] [dry-run|live]" >&2
exit 2
