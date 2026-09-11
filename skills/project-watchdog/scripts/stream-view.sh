#!/usr/bin/env bash
# Colored live view of the watchdog event stream (events.jsonl).
# Green=COMPLETED/UPDATED, red=BLOCKED/FAILED, yellow=NEEDS_ATTENTION, dim=heartbeat.
set -euo pipefail
LOG="${1:-$HOME/.local/state/project-watchdog/events.jsonl}"
exec tail -n "${LINES_BACK:-25}" -F "$LOG" | jq -r --unbuffered '
  def C(c): "\u001b[" + c + "m";
  def R: "\u001b[0m";
  if .kind == "heartbeat" then
    C("2") + "\(.ts) 💓 \(.state) #\(.issue // "-") 🤖 \(.agent // "-") 🧠 \(.model // "-") ⏱ \(.elapsed_s // 0)s" + R
  else
    (if (.status // "") | test("COMPLETED|UPDATED|CLEARED|CLOSED_ON_GITHUB") then C("32;1") + "✅"
     elif (.status // "") | test("BLOCKED|FAILED") then C("31;1") + "❌"
     elif (.status // "") | test("DRY_RUN") then C("36;1") + "🧪"
     else C("33;1") + "⚠️" end) as $c
    | $c + " \(.ts) [\(.status)] \(.repo // "-")#\(.issue // "-")" + R
      + "\n  📝 " + C("37") + "\(.summary // "-")" + R
      + (if .seat then "\n  🤖 " + C("36") + "\(.seat)" + R else "" end)
      + (if .triage then "\n  🏷  " + C("35") + "\(.triage)" + R else "" end)
      + (if (.pydantic // []) | length > 0 then "\n  🐍 " + C("31") + "\(.pydantic | join(" | "))" + R else "" end)
      + "\n" + C("2") + ("-" * 60) + R
  end'
