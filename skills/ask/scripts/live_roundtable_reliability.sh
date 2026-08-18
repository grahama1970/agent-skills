#!/usr/bin/env bash
# Real non-deterministic reliability: run a full live multi-seat roundtable
# N times and judge on DELIVERED output (each seat's node receipt ok + non-empty
# response), read back from the run's join receipt. Prints one PASS/FAIL per
# trial and an aggregate. A trial PASSES iff the join reaches PASS/DEGRADED with
# >= MIN_DELIVERED seats delivering non-empty responses -- three by default,
# which is roundtable quorum, not two.
set -uo pipefail
ASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
N="${1:-6}"
# Quorum is three delivered seats (skills/ask/src/ask/panel_compliance.py
# ROUNDTABLE_MIN_ANSWERING). Two lets a panel that loses a seat report as a
# panel while being one opinion.
MIN_DELIVERED="${MIN_DELIVERED:-3}"
# Dispatch the roster, not the quorum. Seating exactly three and demanding
# three makes every trial a perfect run: at the ~75% per-seat delivery rate on
# record that is a 42% trial pass rate, so the harness would measure browser
# luck rather than roundtable reliability. webclaude is out of credits and
# falls back to the local Claude lane, so it is not counted as a browser seat.
HANDLERS=(${ROUNDTABLE_HANDLERS:-webgpt webkimi webgemini webgrok webdeepseek})
OUT_ROOT="$(mktemp -d)"

hargs=(); for h in "${HANDLERS[@]}"; do hargs+=(--handler "$h"); done

pass=0
TRIAL_DELAY="${TRIAL_DELAY:-0}"
for i in $(seq 1 "$N"); do
  [ "$i" -gt 1 ] && [ "$TRIAL_DELAY" -gt 0 ] && sleep "$TRIAL_DELAY"
  run_out="$OUT_ROOT/trial-$i"
  printf 'In one short paragraph, name one concrete strength of showing a DAG preview before execution. Then stop.\n' > "$OUT_ROOT/req-$i.md"
  timeout 1800 "$ASK_DIR/run.sh" tau-dag "Review: name one concrete strength of showing a DAG preview before execution" \
    --repo grahama1970/agent-skills --target "reliability-r$i" \
    --immutable-goal "Each seat delivers a non-empty on-topic paragraph naming one concrete strength of a pre-execution DAG preview" \
    --workflow-mode roundtable "${hargs[@]}" \
    --run-output-root "$run_out" --execute --poll-timeout-seconds 1620 --json \
    > "$OUT_ROOT/result-$i.json" 2>"$OUT_ROOT/err-$i.txt" || true

  delivered=$(python3 - "$run_out" <<'PY'
import json, sys, glob, os
root = sys.argv[1]
n = 0
for jr in glob.glob(os.path.join(root, "*", "node-artifacts", "join", "node-receipt.json")):
    try:
        r = json.load(open(jr))
    except Exception:
        continue
    for s in r.get("seat_terminal_states", []):
        if s.get("delivered") is True:
            n += 1
print(n)
PY
)
  delivered="${delivered:-0}"
  if [ "$delivered" -ge "$MIN_DELIVERED" ]; then
    echo "trial $i: PASS ($delivered seats delivered)"; pass=$((pass+1))
  else
    echo "trial $i: FAIL ($delivered seats delivered)"
  fi
done
echo "LIVE ROUNDTABLE RELIABILITY: $pass/$N seats>=$MIN_DELIVERED delivered"
pct=$(python3 -c "print(round(100*$pass/$N,1))")
echo "PCT: $pct%"
echo "runs: $OUT_ROOT"
