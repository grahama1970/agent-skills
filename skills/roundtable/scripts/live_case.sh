#!/usr/bin/env bash
# Live e2e: generate a roundtable workflow and execute it through the real
# subagent tool via headless pi; the join synthesis is written to live-out.json
# next to the fixture (independent readback oracle).
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(dirname "$0")/../fixtures/live-out.json"
WF=/tmp/rt-live-fixture.js
rm -f "$OUT"
bash "$DIR/run.sh" --mode roundtable \
  --packet "Answer in one sentence: what does TDZ mean in JavaScript?" \
  --seat flash=zai/glm-5.3-flash --out "$WF" >/dev/null
timeout 540 pi -p --provider zai --model glm-5.3 "Use the subagent tool exactly once with workflowScriptPath '$WF' and async:false. When it returns, use the write tool to write {\"schema\":\"roundtable.live.v1\",\"synthesis\":<the join seat's synthesis text as a JSON string>} to '$OUT'. Do nothing else." >/tmp/rt-live-pi.log 2>&1 || true
# Oracle is the artifact, not pi's exit status (headless pi may not exit promptly after agent_end).
if test -s "$OUT"; then cat "$OUT"; exit 0; fi
grep -q rate_limit /tmp/rt-live-pi.log && { echo LIVE_BLOCKED_RATE_LIMIT; exit 3; }
echo "live-out.json missing"; tail -5 /tmp/rt-live-pi.log >&2; exit 1
