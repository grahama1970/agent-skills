#!/usr/bin/env bash
set -euo pipefail

BATTLE_ID="${BATTLE_ID:-battle-004}"
BATTLE_FIXTURE="${BATTLE_FIXTURE:-/app/skills/battle/spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json}"
BATTLE_ADAPTER_PORT="${BATTLE_ADAPTER_PORT:-50111}"
BATTLE_WEBSOCKET_PORT="${BATTLE_WEBSOCKET_PORT:-57711}"
BATTLE_FRONTEND_PORT="${BATTLE_FRONTEND_PORT:-33707}"

mkdir -p "${BATTLE_STORAGE_ROOT:-/tmp/battle-storage}"

cd /app/skills/battle
./run.sh serve-live-transport \
  --fixture "$BATTLE_FIXTURE" \
  --battle-id "$BATTLE_ID" \
  --host 0.0.0.0 \
  --port "$BATTLE_ADAPTER_PORT" \
  --websocket-port "$BATTLE_WEBSOCKET_PORT" &
adapter_pid=$!

cleanup() {
  if kill -0 "$adapter_pid" >/dev/null 2>&1; then
    kill "$adapter_pid" >/dev/null 2>&1 || true
    wait "$adapter_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:${BATTLE_ADAPTER_PORT}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

curl -fsS "http://127.0.0.1:${BATTLE_ADAPTER_PORT}/healthz" >/dev/null

cd /app/skills/battle/spectator
exec npm run preview -- --host 0.0.0.0 --port "$BATTLE_FRONTEND_PORT"
