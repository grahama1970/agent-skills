#!/usr/bin/env bash
# Interview-day bring-up for the live-evidence copilot (DriveWealth, 2026-08).
# One command: services verified, KB reachable, pack loaded, session started,
# listener on the meeting audio, HUD open. Fail-closed at every step.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${LIVE_EVIDENCE_PORT:-8799}"          # 8765 is owned by task-monitor
BASE="http://127.0.0.1:$PORT"
PACK="$SKILL_DIR/fixtures/briefing_drivewealth.json"

# Room-audio source: default = Jabra microphone input.
# This is the right topology when an iPad plays interview audio through its
# external speaker and the Jabra speakerphone listens to the room. For meeting
# audio rendered by this Linux box, override with INTERVIEW_AUDIO_SOURCE=sink:<output-sink>.
SRC="${INTERVIEW_AUDIO_SOURCE:-auto:jabra-input}"

export LIVE_EVIDENCE_REPOS="$HOME/workspace/experiments/agent-skills:$HOME/workspace/experiments/tau:$HOME/workspace/experiments/memory:$HOME/workspace/experiments/sparta:$HOME/workspace/experiments/dw-openapi"

# Provider access stays inside Ask/Tau; no provider credentials belong here.
export LIVE_EVIDENCE_ASK_RUNNER="${LIVE_EVIDENCE_ASK_RUNNER:-$SKILL_DIR/../ask/run.sh}"
export LIVE_EVIDENCE_ASK_ALLOW_PROVIDER_CALLS=true
export LIVE_EVIDENCE_ASK_TIMEOUT="${LIVE_EVIDENCE_ASK_TIMEOUT:-180}"

echo "== dependency probes"
curl -sf -m 5 http://127.0.0.1:8601/health >/dev/null || { echo "FATAL: memory daemon down"; exit 1; }
curl -sf -m 20 -X POST http://127.0.0.1:8601/recall -H 'Content-Type: application/json' \
  -d '{"q":"drivewealth autopilot rebalancing","limit":1}' | grep -q '"found": *true' \
  || { echo "FATAL: DriveWealth KB not recallable"; exit 1; }

echo "== service"
if ! curl -sf -m 3 "$BASE/api/health" >/dev/null; then
  nohup bash "$SKILL_DIR/run.sh" serve --port "$PORT" >/tmp/live-evidence-interview-day.log 2>&1 &
  for _ in $(seq 1 30); do curl -sf -m 2 "$BASE/api/health" >/dev/null && break; sleep 1; done
fi
curl -sf -m 5 "$BASE/api/health" | grep -q '"repo_count":5' || { echo "FATAL: service unhealthy or wrong repos"; exit 1; }

echo "== doctor"
bash "$SKILL_DIR/run.sh" doctor | grep -q READY_FOR_LIVE || { echo "FATAL: doctor not READY_FOR_LIVE"; exit 1; }

echo "== briefing pack"
curl -sf -m 10 -X POST "$BASE/api/briefing/load" -H 'Content-Type: application/json' \
  -d @"$PACK" | grep -q '"status":"loaded"' || { echo "FATAL: pack rejected"; exit 1; }

echo "== session (meeting purpose, consent confirmed by running this script)"
curl -sf -m 10 -X POST "$BASE/api/session/start" -H 'Content-Type: application/json' \
  -d '{"purpose":"meeting","actor_role":"candidate","consent_confirmed":true}' >/dev/null

echo "== listener on: $SRC"
nohup bash "$SKILL_DIR/run.sh" listen --mode pipewire --pipewire-source "$SRC" \
  --backend-url "$BASE" --speaker interviewer --consent-confirmed \
  >/tmp/live-evidence-interview-listener.log 2>&1 &
echo "listener pid $!"

echo "== HUD: $BASE  (glance top-center; diagrams in fixtures/diagrams/)"
command -v xdg-open >/dev/null && xdg-open "$BASE" >/dev/null 2>&1 || true
echo "READY. GPU note: do not run chatterbox TTS or heavy CUDA jobs during the call."
