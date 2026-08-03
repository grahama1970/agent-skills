#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BATTLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SPECTATOR_DIR="$BATTLE_DIR/spectator"
OUT_DIR="${BATTLE_HUMAN_INTERJECTION_SPECTATOR_PROOF_DIR:-/tmp/battle-human-interjection-spectator-proof}"
BACKEND_DIR="$OUT_DIR/backend"
FIXTURE_DIR="$OUT_DIR/generated-fixtures"
START_PREVIEW=0
SERVER_PID=""
SERVER_LOG=""

port_owner_pid() {
  ss -ltnp 2>/dev/null | awk -v port=":${1}" '$4 ~ port"$" { print $0 }' \
    | sed -nE 's/.*pid=([0-9]+).*/\1/p' \
    | head -n 1
}

choose_preview_port() {
  local port
  for port in $(seq 3026 3035); do
    if [[ -z "$(port_owner_pid "$port")" ]]; then
      echo "$port"
      return 0
    fi
  done
  echo "No free Battle spectator preview port found in 3026-3035." >&2
  return 24
}

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

rm -rf "$BACKEND_DIR" "$FIXTURE_DIR"
mkdir -p "$OUT_DIR" "$BACKEND_DIR" "$FIXTURE_DIR"

if [[ -n "${BATTLE_HOST:-}" ]]; then
  HOST="$BATTLE_HOST"
else
  PORT="$(choose_preview_port)"
  HOST="http://127.0.0.1:${PORT}"
  START_PREVIEW=1
fi
export BATTLE_HOST="$HOST"
export BATTLE_HUMAN_INTERJECTION_SPECTATOR_PROOF_DIR="$OUT_DIR"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${BATTLE_STORAGE_ROOT:-/mnt/storage12tb/skills/battle}/.venv}"
export PYTHONPATH="$BATTLE_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

echo "=== Battle human-interjection spectator proof ==="
echo "battle_dir=$BATTLE_DIR"
echo "spectator_dir=$SPECTATOR_DIR"
echo "host=$HOST"
echo "out_dir=$OUT_DIR"

echo "1/7 Backend pause_after_round receipt proof"
(cd "$BATTLE_DIR" && uv run --project "$BATTLE_DIR" python scripts/human_interjection_proof.py --out-dir "$BACKEND_DIR")

echo "2/7 Generate receipt-derived spectator fixtures"
(cd "$BATTLE_DIR" && uv run --project "$BATTLE_DIR" python scripts/human_interjection_spectator_fixture.py --proof "$BACKEND_DIR/proof.json" --out-dir "$FIXTURE_DIR")

echo "3/7 Spectator dependencies"
if [[ ! -f "$SPECTATOR_DIR/node_modules/.package-lock.json" || "$SPECTATOR_DIR/package-lock.json" -nt "$SPECTATOR_DIR/node_modules/.package-lock.json" ]]; then
  (cd "$SPECTATOR_DIR" && npm install --no-fund --no-audit)
else
  echo "  npm dependencies already present; skipping install"
fi

echo "4/7 Spectator typecheck"
(cd "$SPECTATOR_DIR" && npm run typecheck)

echo "5/7 Human interjection view-model test"
(cd "$SPECTATOR_DIR" && npx vitest run src/lib/battle-human-interjection.test.ts)

if [[ "$START_PREVIEW" == "1" ]]; then
  echo "6/7 Build and serve fresh spectator preview"
  (cd "$SPECTATOR_DIR" && npm run build)
  SERVER_LOG="$OUT_DIR/preview-${PORT}.log"
  (cd "$SPECTATOR_DIR" && npm run preview -- --port "$PORT" --strictPort >"$SERVER_LOG" 2>&1) &
  SERVER_PID=$!
  for _ in $(seq 1 80); do
    if curl -fsS "$HOST" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  curl -fsS "$HOST" >/dev/null
else
  echo "6/7 Using supplied BATTLE_HOST"
fi

echo "7/7 Browser screenshot/readback proof"
(cd "$SPECTATOR_DIR" && npm run prove:human-interjection-panel)

echo "BATTLE_HUMAN_INTERJECTION_SPECTATOR_PROOF_PASS"
