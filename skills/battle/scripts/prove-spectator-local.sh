#!/usr/bin/env bash
# Hard local proof gate for Battle spectator package + backend UX contracts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BATTLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SPECTATOR_DIR="$BATTLE_DIR/spectator"
HOST="${BATTLE_HOST:-http://127.0.0.1:3002}"
export BATTLE_HOST="$HOST"
export BATTLE_PIXI_URL="${BATTLE_PIXI_URL:-$HOST/#battle?engine=pixi}"
export BATTLE_RECEIPT_URL="${BATTLE_RECEIPT_URL:-$HOST/#battle/receipt?engine=pixi}"

export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${BATTLE_STORAGE_ROOT:-/mnt/storage12tb/skills/battle}/.venv}"
export PYTHONPATH="$BATTLE_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

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

echo "8/8 Fresh arena fixture Pixi proof (BATTLE-005/006/007)"
(cd "$SPECTATOR_DIR" && npm run prove:fresh-fixture-replay)

echo "BATTLE_PROVE_SPECTATOR_PASS"
