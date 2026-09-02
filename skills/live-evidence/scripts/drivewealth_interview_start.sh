#!/usr/bin/env bash
# DriveWealth interview day: one command to (re)start the full live path on current code.
# Usage: skills/live-evidence/scripts/drivewealth_interview_start.sh
set -euo pipefail
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SKILL"

BACKEND_URL="http://127.0.0.1:8800"
JABRA_SINK="sink:alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo"
LOG_DIR="/tmp/live-evidence-drivewealth-interview"
mkdir -p "$LOG_DIR"

# 1. Kill stale backend/listener so today's code is what runs.
pkill -f "live_evidence serve --port 8800" 2>/dev/null || true
pkill -f "live_evidence listen --mode pipewire" 2>/dev/null || true
sleep 2

# 2. Scanner key: the 3-agent scanner path activates only when a SciLLM key
#    is present; without it the backend silently uses the legacy question
#    window (root cause of 2026-09-01 live duplicate cards).
SCANNER_KEY="${SCILLM_MASTER_KEY:-$(docker inspect docker-scillm-proxy-1 --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep '^SCILLM_MASTER_KEY=' | cut -d= -f2-)}"
test -n "$SCANNER_KEY" || { echo 'FATAL: no SciLLM key found; scanner path would be silently disabled'; exit 1; }

# 3. Backend with DriveWealth profile + repos.
LIVE_EVIDENCE_PROFILE="$SKILL/config/drivewealth.yaml" \
LIVE_EVIDENCE_SCILLM_KEY="$SCANNER_KEY" \
LIVE_EVIDENCE_REPOS="$HOME/workspace/experiments/dw-openapi:$HOME/workspace/experiments/dwt-terraform-aws-helm-release:$HOME/workspace/experiments/agent-skills" \
  nohup ./run.sh serve --port 8800 > "$LOG_DIR/backend.log" 2>&1 &
echo "backend PID $!"
for _ in $(seq 1 30); do
  curl -sf -m 2 "$BACKEND_URL/api/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf -m 5 "$BACKEND_URL/api/health" || { echo "BACKEND FAILED - read $LOG_DIR/backend.log"; exit 1; }
echo

# 3. Load DriveWealth prep pack.
./run.sh load-prep-pack --pack fixtures/prep_pack_drivewealth.json \
  --backend-url "$BACKEND_URL" --output "$LOG_DIR/prep-load.json"

# 4. Jabra listener (meeting audio -> STT -> cards).
nohup ./run.sh listen --mode pipewire --pipewire-source "$JABRA_SINK" \
  --backend-url "$BACKEND_URL" --speaker interviewer --device cpu --consent-confirmed \
  > "$LOG_DIR/listener.log" 2>&1 &
echo "listener PID $!"

echo
echo "READY. HUD: $BACKEND_URL  Logs: $LOG_DIR/"
