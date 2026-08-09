#!/usr/bin/env bash
# Non-deterministic real-world proof of BIDIRECTIONAL communication with
# another agent's Herdr session: send a challenge, capture the agent's reply.
#
# One-way delivery only proves text arrived. This proves the agent read it and
# answered, which is what "talking to another session" has to mean.
#
# Distinguishing the reply from the echoed prompt is the whole difficulty. The
# nonce appears once when the prompt is echoed into the pane and again when the
# agent answers, so the pass condition is TWO or more occurrences. Counting is
# used rather than matching a reply marker because those are harness-specific
# (codex renders `›` for input and `•` for output; other harnesses differ) and
# the count works across all of them.
#
# The probe skips rather than fails when the environment cannot support it, so
# an eval suite is not red for reasons unrelated to /ask.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERDR="${HERDR_BIN:-$HOME/.local/share/mise/installs/herdr/latest/herdr}"
NONCE="PONG$(date +%s)$$"

[ -x "$HERDR" ] || HERDR="$(command -v herdr 2>/dev/null || true)"
if [ -z "$HERDR" ] || [ ! -x "$HERDR" ]; then echo "SKIP: herdr not installed"; exit 0; fi

panes_json="$("$HERDR" pane list 2>/dev/null)" || { echo "SKIP: herdr not running"; exit 0; }

mapfile -t CANDIDATES < <(printf '%s' "$panes_json" | python3 -c '
import json, sys
try:
    panes = json.load(sys.stdin)["result"]["panes"]
except Exception:
    sys.exit(0)
for p in sorted(panes, key=lambda x: str(x.get("pane_id"))):
    if p.get("agent") and p.get("agent_status") == "idle":
        print(p["pane_id"])
')

# A pane that does not render cannot show a reply. This check is what separates
# a live agent from a process whose UI has died -- herdr reports both as idle.
TARGET=""
for pane in "${CANDIDATES[@]}"; do
  if [ "$("$HERDR" pane read "$pane" --source recent --lines 5 2>/dev/null | wc -c)" -gt 0 ]; then
    TARGET="$pane"; break
  fi
done
[ -n "$TARGET" ] || { echo "SKIP: no rendering idle pane available"; exit 0; }

before="$("$HERDR" pane read "$TARGET" --source recent --lines 300 2>/dev/null | grep -c "$NONCE")"
[ "$before" -eq 0 ] || { echo "SKIP: nonce already present in $TARGET"; exit 0; }

echo "target=$TARGET nonce=$NONCE"
send_out="$(cd "$SKILL_DIR" && ./run.sh herdr send "$TARGET" \
  "Respond with only this token and nothing else: $NONCE" --json 2>&1)"
echo "$send_out"
printf '%s' "$send_out" | grep -q '"submitted": true' || { echo "FAIL: send did not report submission"; exit 1; }

for _ in $(seq 1 12); do
  count="$("$HERDR" pane read "$TARGET" --source recent --lines 300 2>/dev/null | grep -c "$NONCE")"
  if [ "$count" -ge 2 ]; then
    echo "PASS: round-trip confirmed in $TARGET ($count occurrences: prompt echo + agent reply)"
    exit 0
  fi
  sleep 5
done

# One occurrence means the prompt landed but no answer came back. Report it as
# the partial result it is rather than as a delivery failure.
final="$("$HERDR" pane read "$TARGET" --source recent --lines 300 2>/dev/null | grep -c "$NONCE")"
if [ "$final" -eq 1 ]; then
  echo "FAIL: delivered to $TARGET but the agent never replied (one-way only)"
else
  echo "FAIL: nonce never appeared in $TARGET"
fi
exit 1
