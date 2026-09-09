#!/usr/bin/env bash
# Live terminal view of the newest project-watchdog Tau repair run.
# Renders the DAG with per-seat status (fixer/reviewer) via $phart-dag-chart
# and refreshes until the run reaches a terminal state.
#
# Usage: watch-live.sh [--once]
set -euo pipefail
STATE_ROOT="${PROJECT_WATCHDOG_STATE_ROOT:-$HOME/.local/state/project-watchdog}"
PHART="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/phart-dag-chart/run.sh"

PROGRESS=$(ls -t "$STATE_ROOT"/receipts/*/ask/*/tau-receipts/dag-progress.json 2>/dev/null | head -1)
if [ -z "$PROGRESS" ]; then
  echo "no Tau repair runs found under $STATE_ROOT/receipts"
  exit 1
fi
RUN_DIR=$(dirname "$(dirname "$PROGRESS")")
DAG="$RUN_DIR/tau-receipts/source-dag.json"
[ -f "$DAG" ] || DAG="$RUN_DIR/dag.json"

echo "run: $RUN_DIR"
exec "$PHART" watch "$DAG" --progress "$PROGRESS" "$@"
