#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BATTLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SPECTATOR_DIR="$BATTLE_DIR/spectator"
OUT_DIR="${BATTLE_LOCAL_CAMPAIGN_PROOF_DIR:-/tmp/battle-local-campaign-qualification}"
TOKEN="${BATTLE_LIVE_CONTROL_TOKEN:-battle-local-campaign-token}"
FIXTURE="${BATTLE_LOCAL_CAMPAIGN_FIXTURE:-$SPECTATOR_DIR/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json}"
PREVIEW_PID=""
SERVER_PID=""

port_owner_pid() {
  ss -ltnp 2>/dev/null | awk -v port=":${1}" '$4 ~ port"$" { print $0 }' \
    | sed -nE 's/.*pid=([0-9]+).*/\1/p' \
    | head -n 1
}

choose_port() {
  local start="$1"
  local end="$2"
  local port
  for port in $(seq "$start" "$end"); do
    if [[ -z "$(port_owner_pid "$port")" ]]; then
      echo "$port"
      return 0
    fi
  done
  return 24
}

cleanup_server() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  SERVER_PID=""
}

cleanup() {
  cleanup_server
  if [[ -n "$PREVIEW_PID" ]] && kill -0 "$PREVIEW_PID" 2>/dev/null; then
    kill "$PREVIEW_PID" 2>/dev/null || true
    wait "$PREVIEW_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${BATTLE_STORAGE_ROOT:-/mnt/storage12tb/skills/battle}/.venv}"
export PYTHONPATH="$BATTLE_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export BATTLE_LOCAL_CAMPAIGN_PROOF_DIR="$OUT_DIR"
export BATTLE_LIVE_CONTROL_TOKEN="$TOKEN"

PREVIEW_PORT="$(choose_port 3046 3055)"
HOST="http://127.0.0.1:${PREVIEW_PORT}"
export BATTLE_HOST="$HOST"

echo "=== Battle local campaign qualification ==="
echo "out_dir=$OUT_DIR"
echo "host=$HOST"

echo "1/10 Backend focused tests"
(cd "$BATTLE_DIR" && uv run --project "$BATTLE_DIR" pytest -q tests/test_live_transport_server.py -k 'control')

echo "2/10 Spectator dependencies/typecheck/tests/build"
if [[ ! -f "$SPECTATOR_DIR/node_modules/.package-lock.json" || "$SPECTATOR_DIR/package-lock.json" -nt "$SPECTATOR_DIR/node_modules/.package-lock.json" ]]; then
  (cd "$SPECTATOR_DIR" && npm install --no-fund --no-audit)
else
  echo "  npm dependencies already present; skipping install"
fi
(cd "$SPECTATOR_DIR" && npm run typecheck)
(cd "$SPECTATOR_DIR" && npx vitest run src/lib/battle-human-interjection.test.ts src/lib/battle-live-control.test.ts)
(cd "$SPECTATOR_DIR" && npm run build)

echo "3/10 Start spectator preview"
(cd "$SPECTATOR_DIR" && npm run preview -- --port "$PREVIEW_PORT" --strictPort >"$OUT_DIR/preview.log" 2>&1) &
PREVIEW_PID=$!
for _ in $(seq 1 100); do
  if curl -fsS "$HOST" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
curl -fsS "$HOST" >/dev/null

echo "4/10 Start initial campaign adapter"
CONTROL_PORT="$(choose_port 18810 18840)"
READY="$OUT_DIR/ready-initial.json"
export BATTLE_LIVE_CONTROL_READY="$READY"
export BATTLE_LIVE_CONTROL_BASE="http://127.0.0.1:${CONTROL_PORT}"
(cd "$BATTLE_DIR" && uv run --project "$BATTLE_DIR" python scripts/local_campaign_qualification.py serve \
  --fixture "$FIXTURE" \
  --battle-id battle-004 \
  --host 127.0.0.1 \
  --port "$CONTROL_PORT" \
  --auth-token "$TOKEN" \
  --out "$OUT_DIR" \
  --ready "$READY" \
  --mode run >"$OUT_DIR/server-initial.log" 2>&1) &
SERVER_PID=$!
for _ in $(seq 1 100); do
  if [[ -f "$READY" ]] && curl -fsS "$BATTLE_LIVE_CONTROL_BASE/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
test -f "$READY"
curl -fsS "$BATTLE_LIVE_CONTROL_BASE/healthz" >/dev/null

echo "5/10 Browser pause during round 2"
export BATTLE_LOCAL_CAMPAIGN_PHASE=pause
(cd "$SPECTATOR_DIR" && node scripts/prove-battle-local-campaign-qualification.mjs)

echo "6/10 Simulate process exit"
cleanup_server

echo "7/10 Resume from durable checkpoint"
(cd "$BATTLE_DIR" && uv run --project "$BATTLE_DIR" python scripts/local_campaign_qualification.py resume \
  --fixture "$FIXTURE" \
  --battle-id battle-004 \
  --out "$OUT_DIR")

echo "8/10 Start restarted adapter"
CONTROL_PORT="$(choose_port 18841 18870)"
READY="$OUT_DIR/ready-restart.json"
export BATTLE_LIVE_CONTROL_READY="$READY"
export BATTLE_LIVE_CONTROL_BASE="http://127.0.0.1:${CONTROL_PORT}"
(cd "$BATTLE_DIR" && uv run --project "$BATTLE_DIR" python scripts/local_campaign_qualification.py serve \
  --fixture "$FIXTURE" \
  --battle-id battle-004 \
  --host 127.0.0.1 \
  --port "$CONTROL_PORT" \
  --auth-token "$TOKEN" \
  --out "$OUT_DIR" \
  --ready "$READY" \
  --mode serve-only >"$OUT_DIR/server-restart.log" 2>&1) &
SERVER_PID=$!
for _ in $(seq 1 100); do
  if [[ -f "$READY" ]] && curl -fsS "$BATTLE_LIVE_CONTROL_BASE/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
test -f "$READY"
curl -fsS "$BATTLE_LIVE_CONTROL_BASE/healthz" >/dev/null

echo "9/10 Browser reconnect after restart"
export BATTLE_LOCAL_CAMPAIGN_PHASE=reconnect
(cd "$SPECTATOR_DIR" && node scripts/prove-battle-local-campaign-qualification.mjs)

echo "10/10 Aggregate qualification receipt"
(cd "$BATTLE_DIR" && uv run --project "$BATTLE_DIR" python scripts/local_campaign_qualification.py aggregate --out "$OUT_DIR")

echo "BATTLE_LOCAL_CAMPAIGN_QUALIFICATION_PASS"
