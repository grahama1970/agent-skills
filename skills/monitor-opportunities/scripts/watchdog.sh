#!/usr/bin/env bash
# monitor-opportunities self-healing watchdog.
#
# Runs the regression eval suite. If any guard is RED, it dispatches a headless
# code fixer (/ask gpt-5.5-high creator + reviewer) with the exact failure output
# so bug-fixing does not depend on a human remembering. On GREEN it is a no-op.
#
# Designed to be registered on a durable cron (scheduler) or invoked from the
# nightly. Writes a status marker to local/watchdog-status.json every run.
set -uo pipefail
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SKILL_DIR"
mkdir -p local
STATUS="local/watchdog-status.json"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"

REPORT="$(./scripts/run_evals.sh 2>&1)"
if grep -q EVAL_SUITE_GREEN <<<"$REPORT"; then
  printf '{"schema":"monitor_opportunities.watchdog.v1","ts":"%s","state":"GREEN","fixer_dispatched":false}\n' "$TS" >"$STATUS"
  echo "GREEN"
  exit 0
fi

# RED: capture which guards failed and dispatch the fixer.
FAILED="$(grep '^FAIL' <<<"$REPORT" | awk '{print $2}' | paste -sd, -)"
printf '{"schema":"monitor_opportunities.watchdog.v1","ts":"%s","state":"RED","failed":"%s","fixer_dispatched":true}\n' "$TS" "$FAILED" >"$STATUS"
echo "RED: $FAILED — dispatching /ask gpt-5.5-high fixer"

ASK="$SKILL_DIR/../ask/run.sh"
PROMPT="monitor-opportunities regression eval suite is RED. Failing guards: $FAILED.
Full output below. Fix the ROOT CAUSE in the source so each named guard passes
(scripts/<guard>.py), never by weakening the guard, fixture, or oracle. Re-run
./scripts/run_evals.sh until EVAL_SUITE_GREEN, then stop. Do not push to main.

$REPORT"

if [ -x "$ASK" ]; then
  "$ASK" tau-dag --topology sequential --creator gpt-5.5-high --reviewer fable-5-low \
    --goal "$PROMPT" --execute 2>&1 | tail -20 || echo "fixer dispatch failed; RED left for human"
else
  echo "ask runner not found at $ASK; RED recorded, no auto-fix dispatched"
fi
exit 1
