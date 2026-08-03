#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BATTLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SPECTATOR_DIR="$BATTLE_DIR/spectator"
OUT_DIR="${BATTLE_LIVE_HUMAN_INTERJECTION_CONTROL_PROOF_DIR:-/tmp/battle-live-human-interjection-control-proof}"
FIXTURE="${BATTLE_LIVE_CONTROL_FIXTURE:-$SPECTATOR_DIR/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json}"
TOKEN="${BATTLE_LIVE_CONTROL_TOKEN:-battle-live-control-proof-token}"
START_PREVIEW=0
PREVIEW_PID=""
CONTROL_PID=""
PREVIEW_LOG=""
CONTROL_LOG=""

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
  echo "No free port found in ${start}-${end}." >&2
  return 24
}

cleanup() {
  if [[ -n "$CONTROL_PID" ]] && kill -0 "$CONTROL_PID" 2>/dev/null; then
    kill "$CONTROL_PID" 2>/dev/null || true
    wait "$CONTROL_PID" 2>/dev/null || true
  fi
  if [[ -n "$PREVIEW_PID" ]] && kill -0 "$PREVIEW_PID" 2>/dev/null; then
    kill "$PREVIEW_PID" 2>/dev/null || true
    wait "$PREVIEW_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

if [[ -n "${BATTLE_HOST:-}" ]]; then
  HOST="$BATTLE_HOST"
else
  PREVIEW_PORT="$(choose_port 3036 3045)"
  HOST="http://127.0.0.1:${PREVIEW_PORT}"
  START_PREVIEW=1
fi
CONTROL_PORT="$(choose_port 18766 18785)"
READY="$OUT_DIR/live-control-ready.json"
CONTROL_LOG="$OUT_DIR/live-control-server.log"

export BATTLE_HOST="$HOST"
export BATTLE_LIVE_CONTROL_READY="$READY"
export BATTLE_LIVE_CONTROL_BASE="http://127.0.0.1:${CONTROL_PORT}"
export BATTLE_LIVE_CONTROL_TOKEN="$TOKEN"
export BATTLE_LIVE_HUMAN_INTERJECTION_CONTROL_PROOF_DIR="$OUT_DIR"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${BATTLE_STORAGE_ROOT:-/mnt/storage12tb/skills/battle}/.venv}"
export PYTHONPATH="$BATTLE_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

echo "=== Battle live human-interjection control proof ==="
echo "battle_dir=$BATTLE_DIR"
echo "spectator_dir=$SPECTATOR_DIR"
echo "host=$HOST"
echo "live_base=$BATTLE_LIVE_CONTROL_BASE"
echo "out_dir=$OUT_DIR"

echo "1/8 Backend control endpoint tests"
(cd "$BATTLE_DIR" && uv run --project "$BATTLE_DIR" pytest -q tests/test_live_transport_server.py -k 'control')

echo "2/8 Spectator dependencies"
if [[ ! -f "$SPECTATOR_DIR/node_modules/.package-lock.json" || "$SPECTATOR_DIR/package-lock.json" -nt "$SPECTATOR_DIR/node_modules/.package-lock.json" ]]; then
  (cd "$SPECTATOR_DIR" && npm install --no-fund --no-audit)
else
  echo "  npm dependencies already present; skipping install"
fi

echo "3/8 Spectator typecheck"
(cd "$SPECTATOR_DIR" && npm run typecheck)

echo "4/8 Focused spectator tests"
(cd "$SPECTATOR_DIR" && npx vitest run src/lib/battle-human-interjection.test.ts src/lib/battle-live-control.test.ts)

echo "5/8 Build and preview spectator"
if [[ "$START_PREVIEW" == "1" ]]; then
  (cd "$SPECTATOR_DIR" && npm run build)
  PREVIEW_LOG="$OUT_DIR/preview-${PREVIEW_PORT}.log"
  (cd "$SPECTATOR_DIR" && npm run preview -- --port "$PREVIEW_PORT" --strictPort >"$PREVIEW_LOG" 2>&1) &
  PREVIEW_PID=$!
  for _ in $(seq 1 100); do
    if curl -fsS "$HOST" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  curl -fsS "$HOST" >/dev/null
else
  echo "  using supplied BATTLE_HOST"
fi

echo "6/8 Start local Battle live control adapter"
(cd "$BATTLE_DIR" && uv run --project "$BATTLE_DIR" python scripts/serve_live_human_interjection_control.py \
  --fixture "$FIXTURE" \
  --battle-id battle-004 \
  --host 127.0.0.1 \
  --port "$CONTROL_PORT" \
  --auth-token "$TOKEN" \
  --out "$OUT_DIR/backend" \
  --ready "$READY" >"$CONTROL_LOG" 2>&1) &
CONTROL_PID=$!
for _ in $(seq 1 100); do
  if [[ -f "$READY" ]] && curl -fsS "$BATTLE_LIVE_CONTROL_BASE/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
test -f "$READY"
curl -fsS "$BATTLE_LIVE_CONTROL_BASE/healthz" >/dev/null

echo "7/8 Browser click/readback proof"
(cd "$SPECTATOR_DIR" && npm run prove:live-human-interjection-control)

echo "8/8 Proof receipt"
python3 - "$OUT_DIR/proof.json" <<'PY'
import json
import sys
path = sys.argv[1]
receipt = json.load(open(path, encoding="utf-8"))
assert receipt["status"] == "PASS", receipt.get("failed")
assert receipt["mocked"] is False
assert receipt["live"] is True
print(json.dumps({"status": receipt["status"], "receipt": path, "checks": len(receipt["checks"])}, indent=2))
PY

echo "BATTLE_LIVE_HUMAN_INTERJECTION_CONTROL_PROOF_PASS"
