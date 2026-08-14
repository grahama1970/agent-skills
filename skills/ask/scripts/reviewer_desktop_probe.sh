#!/usr/bin/env bash
# Real-world proof that an Ask-provisioned browser window lands on the reviewer
# desktop instead of on top of whatever the human is working on.
#
# Exercises the same three steps Ask's per-seat loop uses -- snapshot, create,
# place -- and then verifies with `wmctrl -lx`, which is a different tool than
# the one that performed the move. browser-oracle reporting "moved" is the tool
# reporting on itself; KDE has been observed bouncing a freshly-mapped window
# back to the active desktop, which is exactly the case a self-report would
# miss.
#
# Always cleans up the window it creates, including on failure.
set -uo pipefail

# One stable result line on every exit path. Without it a graceful SKIP (exit 0,
# no PASS text) is indistinguishable from a failure to an eval asserting on
# output, which is exactly how three green probes read as red when herdr was
# simply not running.
_probe_result_rc() {
  if [ "$1" -eq 0 ]; then echo "PROBE_RESULT: OK (pass or skip)"; else echo "PROBE_RESULT: FAIL rc=$1"; fi
}
_probe_result() { _probe_result_rc "$?"; }
trap _probe_result EXIT

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SURF="$SKILL_DIR/../surf/run.sh"
BO="$SKILL_DIR/../browser-oracle/run.sh"
DESKTOP="${ASK_REVIEWER_DESKTOP:-1}"

command -v wmctrl >/dev/null 2>&1 || { echo "SKIP: wmctrl not installed"; exit 0; }
[ -x "$SURF" ] && [ -x "$BO" ] || { echo "SKIP: surf or browser-oracle unavailable"; exit 0; }

BEFORE="$("$BO" window-snapshot --json 2>/dev/null | python3 -c '
import json, sys
try:
    print(",".join(json.load(sys.stdin)["windows"]))
except Exception:
    pass
')"
[ -n "$BEFORE" ] || { echo "SKIP: could not snapshot chrome windows"; exit 0; }

cleanup() {
  local rc=$?
  # Window first: a probe that leaks its window is worse than one that reports
  # late. Then the result line, since a second `trap ... EXIT` would otherwise
  # silently replace the earlier handler rather than adding to it.
  [ -n "${TARGET:-}" ] && wmctrl -i -c "$TARGET" 2>/dev/null
  _probe_result_rc "$rc"
}
trap cleanup EXIT

"$SURF" window.new "https://chatgpt.com/" --json --unfocused >/dev/null 2>&1 || {
  echo "SKIP: could not create a browser window"; exit 0; }
sleep 3

PLACED="$("$BO" place-window --before "$BEFORE" --desktop "$DESKTOP" --json 2>/dev/null)"
echo "$PLACED"
TARGET="$(printf '%s' "$PLACED" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("window") or "")
except Exception:
    pass
')"
[ -n "$TARGET" ] || { echo "FAIL: placement reported no window"; exit 1; }

# The independent half: ask the window manager directly.
ACTUAL="$(wmctrl -lx 2>/dev/null | awk -v w="$TARGET" 'tolower($1)==tolower(w){print $2}')"
if [ "$ACTUAL" = "$DESKTOP" ]; then
  echo "PASS: $TARGET is on desktop index $ACTUAL (verified by wmctrl, not by the mover)"
  exit 0
fi
echo "FAIL: $TARGET is on desktop '$ACTUAL', expected '$DESKTOP'"
exit 1
