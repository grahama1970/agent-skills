#!/usr/bin/env bash
set -euo pipefail

log="${PROJECT_WATCHDOG_LOG:-$HOME/.local/state/project-watchdog-v2/events.jsonl}"
lines="${PROJECT_WATCHDOG_STREAM_LINES:-30}"

mkdir -p "$(dirname "$log")"
touch "$log"

echo "project-watchdog V2 events: $log" >&2
if command -v jq >/dev/null 2>&1; then
  tail -n "$lines" -F "$log" | jq --unbuffered -r '
    [.at, (.ticket // .project // "-"), .stage, .status,
     (.reason // (if (.command | type) == "array" then (.command | join(" ")) else .command end) // (.triage.code // ""))]
    | @tsv'
else
  tail -n "$lines" -F "$log"
fi
