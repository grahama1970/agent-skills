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

echo "1/10 Backend contract pytest"
(cd "$BATTLE_DIR" && uv run pytest tests/test_battle_event_adapter_contract.py -q)

echo "2/10 Live lifecycle receipt contract pytest"
(cd "$BATTLE_DIR" && uv run pytest tests/test_arena_live_battle_proof_contract.py -q)

echo "3/10 Exploit combiner specimen proof"
(cd "$BATTLE_DIR" && uv run pytest tests/test_exploit_combiner_contract.py tests/test_exploit_specimen_receipts.py -q)
COMBINER_DIR="$ARTIFACT_DIR/battle-004-combiner"
rm -rf "$COMBINER_DIR"
uv run --project "$BATTLE_DIR" python -m battle_skill.cli exploit-combiner-proof battle-004 --out "$COMBINER_DIR" --max-attempts 4
python3 -c 'import json, pathlib, sys; root = pathlib.Path(sys.argv[1]); receipt = json.loads((root / "run-receipt.json").read_text()); assert receipt["proof_mode"] == "local_docker_specimen_fixture"; assert receipt["agentic"] is False; assert receipt["scoreboard"]["verdict"] == "RUNNABLE_UNPROVEN"; assert receipt["scoreboard"]["judge_verified_exploits"] == 0; assert "Any specimen exploited the target." in receipt["claims"]["does_not_prove"]' "$COMBINER_DIR"

echo "4/10 Spawn Architect DAG birth proof"
(cd "$BATTLE_DIR" && uv run pytest tests/test_child_knowledge_packet_contract.py tests/test_child_tau_dag_private_boundary.py tests/test_spawn_architect_contract.py -q)
SPAWN_ARCHITECT_DIR="$ARTIFACT_DIR/battle-004-spawn-architect"
rm -rf "$SPAWN_ARCHITECT_DIR"
uv run --project "$BATTLE_DIR" python -m battle_skill.cli spawn-architect-proof battle-004 --out "$SPAWN_ARCHITECT_DIR" --parent-combiner-proof "$COMBINER_DIR"
python3 -c 'import json, pathlib, sys; root = pathlib.Path(sys.argv[1]); receipt = json.loads((root / "spawn-architect-receipt.json").read_text()); assert receipt["proof_mode"] == "spawn_architect_fixture_dag_birth"; assert receipt["agentic"] is False; assert receipt["tau_execution"] == "deferred_to_pr3"; assert receipt["validation"]["private_boundary_passed"] is True; assert receipt["scoreboard"]["live_tau_executions"] == 0; assert receipt["scoreboard"]["child_exploits_materialized"] == 0; assert receipt["scoreboard"]["judge_verified_exploits"] == 0; assert "Any exploit succeeded." in receipt["claims"]["does_not_prove"]' "$SPAWN_ARCHITECT_DIR"

echo "5/10 Semantic outcome matrix export/validate"
SEMANTIC_MATRIX="$ARTIFACT_DIR/battle-semantic-outcome-matrix.json"
uv run --project "$BATTLE_DIR" python -m battle_skill.cli export-semantic-outcome-matrix --out "$SEMANTIC_MATRIX"
uv run --project "$BATTLE_DIR" python -m battle_skill.cli validate-semantic-outcome-matrix "$SEMANTIC_MATRIX"

echo "6/10 Exploit lifecycle DAG export/validate"
LIFECYCLE_DAG="$ARTIFACT_DIR/battle-exploit-lifecycle-dag.json"
uv run --project "$BATTLE_DIR" python -m battle_skill.cli export-exploit-lifecycle-dag --out "$LIFECYCLE_DAG"
uv run --project "$BATTLE_DIR" python -m battle_skill.cli validate-exploit-lifecycle-dag "$LIFECYCLE_DAG"

echo "7/10 Normalized UX fixture validation"
for fixture in \
  "$BATTLE_DIR/local/battle-004-parent-spawn.normalized.json" \
  "$BATTLE_DIR/local/battle-004-sparse.normalized.json" \
  "$BATTLE_DIR/local/battle-005-ssrf-metadata.normalized.json" \
  "$BATTLE_DIR/local/battle-006-pickle-deserialization.normalized.json" \
  "$BATTLE_DIR/local/battle-007-file-upload.normalized.json"; do
  echo "  validate-ux-contract $fixture"
  uv run --project "$BATTLE_DIR" python -m battle_skill.cli validate-ux-contract "$fixture"
done

echo "8/10 Phase 2 transport stream validation"
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

echo "9/10 Spectator replay proof"
"$BATTLE_DIR/scripts/prove-spectator-local.sh"

echo "10/10 Mock evidence claim guard"
(cd "$(cd "$BATTLE_DIR/../.." && pwd)" && python3 scripts/check_mock_evidence_claims.py)

echo "BATTLE_PROVE_BACKEND_GOAL_PASS"
