#!/usr/bin/env bash
# Hard local proof gate for the active Battle backend goal.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BATTLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ARTIFACT_DIR="${BATTLE_BACKEND_GOAL_PROOF_DIR:-/tmp/battle-backend-goal-proof}"
HOST="${BATTLE_HOST:-http://127.0.0.1:3002}"

export BATTLE_HOST="$HOST"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${BATTLE_STORAGE_ROOT:-/mnt/storage12tb/skills/battle}/.venv}"
export PYTHONPATH="$BATTLE_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$ARTIFACT_DIR"

echo "=== Battle prove-backend-goal-local ==="
echo "battle_dir=$BATTLE_DIR"
echo "artifact_dir=$ARTIFACT_DIR"
echo "host=$HOST"

echo "1/7 Backend contract pytest"
(cd "$BATTLE_DIR" && uv run pytest tests/test_battle_event_adapter_contract.py -q)

echo "2/7 Semantic outcome matrix export/validate"
SEMANTIC_MATRIX="$ARTIFACT_DIR/battle-semantic-outcome-matrix.json"
uv run --project "$BATTLE_DIR" python -m battle_skill.cli export-semantic-outcome-matrix --out "$SEMANTIC_MATRIX"
uv run --project "$BATTLE_DIR" python -m battle_skill.cli validate-semantic-outcome-matrix "$SEMANTIC_MATRIX"

echo "3/7 Exploit lifecycle DAG export/validate"
LIFECYCLE_DAG="$ARTIFACT_DIR/battle-exploit-lifecycle-dag.json"
uv run --project "$BATTLE_DIR" python -m battle_skill.cli export-exploit-lifecycle-dag --out "$LIFECYCLE_DAG"
uv run --project "$BATTLE_DIR" python -m battle_skill.cli validate-exploit-lifecycle-dag "$LIFECYCLE_DAG"

echo "4/7 Normalized UX fixture validation"
for fixture in \
  "$BATTLE_DIR/local/battle-004-parent-spawn.normalized.json" \
  "$BATTLE_DIR/local/battle-004-sparse.normalized.json" \
  "$BATTLE_DIR/local/battle-005-ssrf-metadata.normalized.json" \
  "$BATTLE_DIR/local/battle-006-pickle-deserialization.normalized.json" \
  "$BATTLE_DIR/local/battle-007-file-upload.normalized.json"; do
  echo "  validate-ux-contract $fixture"
  uv run --project "$BATTLE_DIR" python -m battle_skill.cli validate-ux-contract "$fixture"
done

echo "5/7 Phase 2 transport stream validation"
for stream_dir in \
  "$BATTLE_DIR/local/battle-004-parent-spawn-pixi-replay/stream" \
  "$BATTLE_DIR/local/battle-005-ssrf-metadata-stream" \
  "$BATTLE_DIR/local/battle-006-pickle-deserialization-stream" \
  "$BATTLE_DIR/local/battle-007-file-upload-stream" \
  "$BATTLE_DIR/spectator/public/battle-fixtures/battle-005-ssrf-metadata-pixi-replay/stream" \
  "$BATTLE_DIR/spectator/public/battle-fixtures/battle-006-pickle-deserialization-pixi-replay/stream" \
  "$BATTLE_DIR/spectator/public/battle-fixtures/battle-007-file-upload-pixi-replay/stream"; do
  echo "  validate-ux-transport $stream_dir"
  uv run --project "$BATTLE_DIR" python -m battle_skill.cli validate-ux-transport "$stream_dir"
done

echo "6/7 Spectator replay proof"
"$BATTLE_DIR/scripts/prove-spectator-local.sh"

echo "7/7 Mock evidence claim guard"
(cd "$(cd "$BATTLE_DIR/../.." && pwd)" && python3 scripts/check_mock_evidence_claims.py)

echo "BATTLE_PROVE_BACKEND_GOAL_PASS"
