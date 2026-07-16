#!/usr/bin/env bash
# Hard local proof gate for Battle spectator package + backend UX contracts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BATTLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SPECTATOR_DIR="$BATTLE_DIR/spectator"
HOST="${BATTLE_HOST:-http://127.0.0.1:3002}"
export BATTLE_HOST="$HOST"
export BATTLE_PIXI_URL="${BATTLE_PIXI_URL:-$HOST/#battle?engine=pixi}"
export BATTLE_RECEIPT_URL="${BATTLE_RECEIPT_URL:-$HOST/#battle/receipt?engine=pixi&fixture=battle-004-parent-spawn-lifecycle}"

export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${BATTLE_STORAGE_ROOT:-/mnt/storage12tb/skills/battle}/.venv}"
export PYTHONPATH="$BATTLE_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export BATTLE_LIVE_TRANSPORT_BASE="${BATTLE_LIVE_TRANSPORT_BASE:-http://127.0.0.1:18765}"

LIVE_TRANSPORT_PID=""
cleanup_live_transport() {
  if [[ -n "$LIVE_TRANSPORT_PID" ]]; then
    kill "$LIVE_TRANSPORT_PID" 2>/dev/null || true
    wait "$LIVE_TRANSPORT_PID" 2>/dev/null || true
    LIVE_TRANSPORT_PID=""
  fi
}
trap cleanup_live_transport EXIT

live_transport_healthy() {
  python3 - "$BATTLE_LIVE_TRANSPORT_BASE" <<'PY'
import json
import sys
import urllib.error
import urllib.request

base = sys.argv[1].rstrip("/")
try:
    with urllib.request.urlopen(f"{base}/healthz", timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8"))
except (OSError, urllib.error.URLError, json.JSONDecodeError):
    sys.exit(1)
schema = payload.get("schema")
if (
    schema in {"battle.live_transport_health.v1", "battle.live_transport_healthz.v1"}
    and payload.get("status") == "PASS"
    and payload.get("battle_id") == "battle-004"
):
    sys.exit(0)
sys.exit(1)
PY
}

ensure_live_transport() {
  if live_transport_healthy; then
    echo "live_transport=already_running base=$BATTLE_LIVE_TRANSPORT_BASE"
    return
  fi

  local port
  port="${BATTLE_LIVE_TRANSPORT_BASE##*:}"
  port="${port%%/*}"
  echo "live_transport=starting base=$BATTLE_LIVE_TRANSPORT_BASE"
  (cd "$BATTLE_DIR" && ./run.sh serve-live-transport --port "$port") >/tmp/battle-live-transport-proof.log 2>&1 &
  LIVE_TRANSPORT_PID="$!"
  for _ in {1..30}; do
    if live_transport_healthy; then
      echo "live_transport=started pid=$LIVE_TRANSPORT_PID base=$BATTLE_LIVE_TRANSPORT_BASE"
      return
    fi
    sleep 0.5
  done
  echo "live_transport=failed base=$BATTLE_LIVE_TRANSPORT_BASE log=/tmp/battle-live-transport-proof.log" >&2
  tail -80 /tmp/battle-live-transport-proof.log >&2 || true
  return 1
}

echo "=== Battle prove-spectator-local ==="
echo "battle_dir=$BATTLE_DIR"
echo "spectator_dir=$SPECTATOR_DIR"
echo "host=$HOST"

echo "1/8 Backend UX contract validation"
for fixture in \
  "$BATTLE_DIR/local/battle-004-parent-spawn.normalized.json" \
  "$BATTLE_DIR/local/battle-004-sparse.normalized.json" \
  "$BATTLE_DIR/local/battle-005-ssrf-metadata.normalized.json" \
  "$BATTLE_DIR/local/battle-006-pickle-deserialization.normalized.json" \
  "$BATTLE_DIR/local/battle-007-file-upload.normalized.json"; do
  echo "  validate-ux-contract $fixture"
  uv run --project "$BATTLE_DIR" python -m battle_skill.cli validate-ux-contract "$fixture"
done

echo "2/8 UX handoff summary"
uv run --project "$BATTLE_DIR" python -m battle_skill.cli validate-ux-handoff-summary \
  "$BATTLE_DIR/local/battle-004-ux-json-contract-summary.json"

echo "3/8 Spectator typecheck"
(cd "$SPECTATOR_DIR" && npm install --no-fund --no-audit && npm run typecheck)

echo "4/8 Spectator Vitest"
(cd "$SPECTATOR_DIR" && npm test)

echo "5/8 Sparse fixture negative gate"
(cd "$SPECTATOR_DIR" && npm run prove:sparse-negative)

echo "6/8 Pixi design route sanity"
(cd "$SPECTATOR_DIR" && npm run prove:pixi)

echo "7/8 Receipt replay Pixi proof (6 requirements)"
(cd "$SPECTATOR_DIR" && npm run prove:receipt-replay)

echo "8/13 Fresh arena fixture Pixi proof (BATTLE-005/006/007)"
(cd "$SPECTATOR_DIR" && npm run prove:fresh-fixture-replay)

echo "9/13 Hunger Games death notification UX proof"
(cd "$SPECTATOR_DIR" && npm run prove:hg-death-notification)

echo "10/13 Hunger Games kill-cue replay proof"
(cd "$SPECTATOR_DIR" && npm run prove:hg-kill-cue-replay)

echo "11/15 No-mockup-leakage receipt chrome proof"
(cd "$SPECTATOR_DIR" && npm run prove:no-mockup-leakage)

echo "12/15 Lifecycle-enriched fixture proof"
(cd "$BATTLE_DIR" && ./run.sh exploit-combiner-proof battle-004 --out /tmp/battle-004-combiner)
(cd "$BATTLE_DIR" && python3 scripts/enrich_pixi_replay_lifecycle.py)
(cd "$SPECTATOR_DIR" && npm run prove:receipt-lifecycle-emitted)

echo "13/15 Pixi kill-shot animation proof"
(cd "$SPECTATOR_DIR" && npm run prove:kill-shot-pixi)

echo "14/19 PR3b proof-card route proof"
(cd "$SPECTATOR_DIR" && npm run prove:pr3b-proof-card)

echo "15/19 Shared view-fixture loader proof"
(cd "$SPECTATOR_DIR" && npm run prove:view-fixture-loader)

echo "16/19 PR3c synthesis route proof"
(cd "$SPECTATOR_DIR" && npm run prove:pr3c-synthesis)

echo "17/19 PR3d compile route proof"
(cd "$SPECTATOR_DIR" && npm run prove:pr3d-compile)

echo "18/19 PR4 runtime/Judge route proof"
(cd "$SPECTATOR_DIR" && npm run prove:pr4-runtime)

echo "19/19 PR5 population route proof"
(cd "$SPECTATOR_DIR" && npm run prove:pr5-population)

echo "XX/XX PR6 genetic Pixi lifecycle proof"
(cd "$SPECTATOR_DIR" && npm run prove:pr6-genetic-pixi)

echo "XX/XX PR8 live transport proof"
ensure_live_transport
(cd "$SPECTATOR_DIR" && npm run prove:pr8-live-transport)

echo "BATTLE_PROVE_SPECTATOR_PASS"
