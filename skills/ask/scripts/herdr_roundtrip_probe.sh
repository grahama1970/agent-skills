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
  [ "$("$HERDR" pane read "$pane" --source recent --lines 5 2>/dev/null | wc -c)" -gt 0 ] || continue
  # Quiescence, not agent_status: herdr reports idle between the turns of an
  # active task. Sample the screen twice and skip anything still redrawing, so
  # a probe never lands in a pane doing real work.
  d1="$("$HERDR" pane read "$pane" --source recent --lines 60 2>/dev/null | sha256sum)"
  sleep 5
  d2="$("$HERDR" pane read "$pane" --source recent --lines 60 2>/dev/null | sha256sum)"
  if [ "$d1" != "$d2" ]; then
    echo "skipping $pane: screen still changing (work in flight)"
    continue
  fi
  # No composer heuristic here on purpose. Matching the last `>`/`›` line was
  # tried and is wrong in both directions: it reads a harness's TRANSCRIPT of
  # the previously submitted prompt as if it were live input, and it flags
  # greyed placeholder hints ("Implement {feature}") as real text. Quiescence
  # above is the signal that holds across harnesses; delivery is verified
  # afterwards rather than predicted beforehand.
  TARGET="$pane"; break
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

final="$("$HERDR" pane read "$TARGET" --source recent --lines 300 2>/dev/null | grep -c "$NONCE")"
tail_text="$("$HERDR" pane read "$TARGET" --source recent --lines 40 2>/dev/null)"

# An agent that cannot answer for provider reasons is not an /ask defect.
# Observed live: delivery landed verbatim at the prompt and the reply never
# came because the pane was out of usage credits. Reporting that as FAIL would
# make the suite red for someone else's billing.
if printf '%s' "$tail_text" | grep -qiE "out of usage credits|usage limit|weekly limit|rate limit|quota"; then
  echo "SKIP: $TARGET received the message but cannot reply (provider limit reached)"
  exit 0
fi

if [ "$final" -eq 1 ]; then
  # Delivery is confirmed; only the reply is missing. Say which half worked.
  echo "FAIL: delivered to $TARGET but the agent never replied (one-way only)"
else
  echo "FAIL: nonce never appeared in $TARGET"
fi
exit 1
