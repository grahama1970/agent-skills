# Issue 1048 Proof: Canonical Dual-Team Fixture

Issue: https://github.com/grahama1970/agent-skills/issues/1048
Date: 2026-07-28

## Files Updated

- `skills/battle/src/battle_skill/normalized_adaptive_lineage_fixture.py`
- `skills/battle/schemas/battle.normalized_adaptive_lineage_fixture.v1.schema.json`
- `skills/battle/tests/test_normalized_adaptive_lineage_fixture.py`
- `skills/battle/local/battle-004-adaptive-lineage-v13/battle.normalized_ux_fixture.json`
- `skills/battle/local/battle-004-adaptive-lineage-v13/validation.json`
- `skills/battle/spectator/public/battle-fixtures/battle-004-adaptive-lineage-v13/battle.normalized_ux_fixture.json`

## What Changed

The V13 normalized fixture now carries a backend-owned canonical dual-team
contract:

- `mechanics_trees` with Red and Blue parent/child nodes;
- same-team Red and Blue lineage edges;
- per-child genome delta, observation, fitness, and selection receipt refs;
- explicit isolation summary with zero cross-team edges;
- `scoreboard` recomputable from named Judge verdict receipt refs;
- `canonical_dual_team_contract` summarizing the read-back gate.

## Deterministic Proof

```text
cd skills/battle
uv run pytest tests/test_normalized_adaptive_lineage_fixture.py tests/test_adaptive_red_blue_lineage_canary_contract.py
```

Result: 6 passed.

```text
cd skills/battle
uv run python - <<'PY'
... validate_canonical_dual_team_fixture(...)
PY
```

Result:

```json
{
  "status": "PASS",
  "local_public_byte_identical": true,
  "red_node_count": 2,
  "blue_node_count": 2,
  "red_edge_count": 1,
  "blue_edge_count": 1,
  "cross_team_edge_count": 0,
  "score_status": "PASS",
  "red_score": 0,
  "blue_score": 2,
  "resolved_reference_count": 20,
  "fixture_sha256": "bb7f8876d2f44c6072097a065b9a1cec11c85af2115e1fee14d1cdf1326c95ba"
}
```

```text
cd skills/battle
./run.sh backend-eval --out-dir local/backend-eval-issue1063-retired-20260728-r2 --allow-live
```

Result: status `passed`, 13 passed / 0 failed / 13 total.

mocked: no
live: no
actually exercised: canonical fixture read-back, schema-backed fixture write,
source-index reference resolution, isolation negative test, score recomputation,
and deterministic backend eval
remains unverified: live regeneration from a fresh Tau/SciLLM/Docker run was not
performed; this ticket scope used the existing source-run fixture already present
on main
