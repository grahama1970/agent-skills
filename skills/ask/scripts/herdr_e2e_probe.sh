#!/usr/bin/env bash
# Non-deterministic real-world proof that /ask can reach another agent's
# Herdr session.
#
# Deliberately end-to-end and unmocked: it picks a live pane from whatever
# Herdr currently reports, sends through `ask herdr send`, then reads the pane
# back through a DIFFERENT command to confirm the text arrived. The readback is
# the point -- `herdr pane run` returning 0 is the tool reporting on itself,
# and during development that exit code was 0 for a pane whose content never
# showed the message.
#
# Pane selection is dynamic because the workstation's 122 panes change between
# runs; there is no fixture to pin. The probe skips (exit 0) rather than failing
# when the environment cannot support it -- Herdr down, or no readable idle
# pane -- so an eval suite is not red for reasons unrelated to /ask.
#
# Only `claude` and `codex` panes are eligible: every `opencode` pane observed
# returns 0 bytes from `pane read`, so delivery there cannot be confirmed and a
# pass would be indistinguishable from a silent failure.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERDR="${HERDR_BIN:-$HOME/.local/share/mise/installs/herdr/latest/herdr}"
MARK="ASKE2E$(date +%s)$$"

command -v "$HERDR" >/dev/null 2>&1 || HERDR="$(command -v herdr 2>/dev/null || true)"
if [ -z "$HERDR" ] || [ ! -x "$HERDR" ]; then
  echo "SKIP: herdr not installed"; exit 0
fi

panes_json="$("$HERDR" pane list 2>/dev/null)" || { echo "SKIP: herdr not running"; exit 0; }

# Idle claude/codex panes only, in a stable order so reruns behave the same.
mapfile -t CANDIDATES < <(printf '%s' "$panes_json" | python3 -c '
import json, sys
try:
    panes = json.load(sys.stdin)["result"]["panes"]
except Exception:
    sys.exit(0)
for p in sorted(panes, key=lambda x: str(x.get("pane_id"))):
    if p.get("agent") in {"claude", "codex"} and p.get("agent_status") == "idle":
        print(p["pane_id"])
')

if [ "${#CANDIDATES[@]}" -eq 0 ]; then
  echo "SKIP: no idle claude/codex pane available"; exit 0
fi

# Try several candidates. The claim under test is that /ask delivers to a
# session, not that one particular pane is healthy; a pane that turns out to be
# unreadable, busy, or wedged is a reason to move on, not to fail.
attempt=0
for pane in "${CANDIDATES[@]}"; do
  [ "$attempt" -lt 3 ] || break
  # Readable BEFORE anything is sent: a pane that cannot be read cannot prove
  # delivery, and discovering that afterwards would strand a message.
  [ "$("$HERDR" pane read "$pane" --source recent --lines 5 2>/dev/null | wc -c)" -gt 0 ] || continue

  # Quiescence, not agent_status: herdr reports idle between the turns of an
  # active task. Sample twice and skip anything still redrawing, so a probe
  # never lands in a pane doing real work.
  d1="$("$HERDR" pane read "$pane" --source recent --lines 60 2>/dev/null | sha256sum)"
  sleep 5
  d2="$("$HERDR" pane read "$pane" --source recent --lines 60 2>/dev/null | sha256sum)"
  if [ "$d1" != "$d2" ]; then
    echo "skipping $pane: screen still changing (work in flight)"
    continue
  fi

  MARK="ASKE2E$(date +%s)$$$attempt"
  attempt=$((attempt + 1))
  echo "target=$pane marker=$MARK"

  send_out="$(cd "$SKILL_DIR" && ./run.sh herdr send "$pane" \
    "Ignore this, no action needed: /ask herdr e2e probe $MARK" --json 2>&1)"
  echo "$send_out"
  printf '%s' "$send_out" | grep -q '"submitted": true' || {
    echo "skipping $pane: send did not report submission"; continue; }

  # The independent half. Poll briefly: rendering is not instant, and a single
  # immediate read would flake on a slow pane.
  for _ in 1 2 3 4 5 6 7 8; do
    if "$HERDR" pane read "$pane" --source recent --lines 120 2>/dev/null | grep -q "$MARK"; then
      echo "PASS: marker present in $pane after delivery through /ask"
      exit 0
    fi
    sleep 2
  done
  # submitted: true is herdr reporting on itself; observed once for a message
  # a harness left unsent in its composer.
  echo "skipping $pane: reported submitted but $MARK never rendered"
done

if [ "$attempt" -eq 0 ]; then
  echo "SKIP: no rendering, settled pane was available to probe"
  exit 0
fi
echo "FAIL: $attempt pane(s) accepted the message and none showed it"
exit 1
