#!/usr/bin/env bash
# Hard local proof gate for Battle spectator package + backend UX contracts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BATTLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SPECTATOR_DIR="$BATTLE_DIR/spectator"
START_PREVIEW=0
SERVER_PID=""
SERVER_LOG=""

port_owner_pid() {
  ss -ltnp 2>/dev/null | awk -v port=":${1}" '$4 ~ port"$" { print $0 }' \
    | sed -nE 's/.*pid=([0-9]+).*/\1/p' \
    | head -n 1
}

choose_preview_port() {
  if [[ -n "${BATTLE_SPECTATOR_PORT:-}" ]]; then
    if [[ -n "$(port_owner_pid "$BATTLE_SPECTATOR_PORT")" ]]; then
      echo "Requested Battle spectator port ${BATTLE_SPECTATOR_PORT} is already in use." >&2
      return 23
    fi
    echo "$BATTLE_SPECTATOR_PORT"
    return 0
  fi
  local port
  for port in $(seq 3016 3025); do
    if [[ -z "$(port_owner_pid "$port")" ]]; then
      echo "$port"
      return 0
    fi
  done
  echo "No free Battle spectator preview port found in 3016-3025." >&2
  return 24
}

if [[ -n "${BATTLE_HOST:-}" ]]; then
  HOST="$BATTLE_HOST"
else
  PORT="$(choose_preview_port)"
  HOST="http://127.0.0.1:${PORT}"
  START_PREVIEW=1
fi
export BATTLE_HOST="$HOST"
export BATTLE_PIXI_URL="${BATTLE_PIXI_URL:-$HOST/#battle?engine=pixi}"
export BATTLE_RECEIPT_URL="${BATTLE_RECEIPT_URL:-$HOST/#battle/receipt?engine=pixi&fixture=battle-004-parent-spawn}"

export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${BATTLE_STORAGE_ROOT:-/mnt/storage12tb/skills/battle}/.venv}"
export PYTHONPATH="$BATTLE_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

echo "=== Battle prove-spectator-local ==="
echo "battle_dir=$BATTLE_DIR"
echo "spectator_dir=$SPECTATOR_DIR"
echo "host=$HOST"

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

enrich_lifecycle_fixture() {
  if [[ -n "${BATTLE_COMBINER_DIR:-}" ]]; then
    (cd "$BATTLE_DIR" && python3 scripts/enrich_pixi_replay_lifecycle.py --combiner-dir "$BATTLE_COMBINER_DIR")
  else
    (cd "$BATTLE_DIR" && python3 scripts/enrich_pixi_replay_lifecycle.py)
  fi
}

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
if [[ ! -f "$SPECTATOR_DIR/node_modules/.package-lock.json" || "$SPECTATOR_DIR/package-lock.json" -nt "$SPECTATOR_DIR/node_modules/.package-lock.json" ]]; then
  (cd "$SPECTATOR_DIR" && npm install --no-fund --no-audit)
else
  echo "  npm dependencies already present; skipping install"
fi
(cd "$SPECTATOR_DIR" && npm run typecheck)

echo "4/8 Spectator Vitest"
(cd "$SPECTATOR_DIR" && npm test)

if [[ "$START_PREVIEW" == "1" ]]; then
  echo "4b/8 Build and serve Battle spectator preview"
  if [[ -n "${BATTLE_COMBINER_DIR:-}" ]]; then
    echo "  prebuild lifecycle enrichment from $BATTLE_COMBINER_DIR"
    enrich_lifecycle_fixture
  fi
  (cd "$SPECTATOR_DIR" && npm run build)
  SERVER_LOG="$BATTLE_DIR/local/prove-spectator-preview-${PORT}.log"
  (cd "$SPECTATOR_DIR" && npm run preview -- --port "$PORT" --strictPort >"$SERVER_LOG" 2>&1) &
  SERVER_PID=$!
  for _ in $(seq 1 80); do
    if curl -fsS "$HOST" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  curl -fsS "$HOST" >/dev/null
fi

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
enrich_lifecycle_fixture
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
(cd "$SPECTATOR_DIR" && npm run prove:pr8-live-transport)

echo "XX/XX V13 adaptive lineage Pixi proof"
(cd "$SPECTATOR_DIR" && npm run prove:adaptive-lineage-v13)

echo "BATTLE_PROVE_SPECTATOR_PASS"
