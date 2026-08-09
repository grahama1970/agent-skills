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

TARGET=""
for pane in "${CANDIDATES[@]}"; do
  # Readable now, before anything is sent: a pane that cannot be read cannot
  # prove delivery, and discovering that afterwards would strand a message.
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

if [ -z "$TARGET" ]; then
  echo "SKIP: no readable idle pane (all candidates returned empty)"; exit 0
fi

echo "target=$TARGET marker=$MARK"

send_out="$(cd "$SKILL_DIR" && ./run.sh herdr send "$TARGET" \
  "Ignore this, no action needed: /ask herdr e2e probe $MARK" --json 2>&1)"
echo "$send_out"

if ! printf '%s' "$send_out" | grep -q '"submitted": true'; then
  echo "FAIL: ask herdr send did not report submission"; exit 1
fi

# The independent half. Poll briefly: rendering is not instant, and a single
# immediate read would flake on a slow pane.
for _ in 1 2 3 4 5 6 7 8; do
  if "$HERDR" pane read "$TARGET" --source recent --lines 120 2>/dev/null | grep -q "$MARK"; then
    echo "PASS: marker present in $TARGET after delivery through /ask"
    exit 0
  fi
  sleep 2
done

echo "FAIL: ask reported submitted but $MARK never appeared in $TARGET"
exit 1
