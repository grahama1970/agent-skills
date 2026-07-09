# Battle Backend Handoff

Timestamp: 2026-07-07T19:24:00-04:00
Authoring agent: Codex
Scope: BATTLE backend/schema/fixture contract only. UX layout and Pixi rendering implementation are owned by the UX project agent.

## Current Objective

Provide backend-generated Battle Arena fixtures that the Pixi spectator UX can replay without inventing client-side battle truth.

The canonical Phase 1 replay fixture is:

```text
http://localhost:3002/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json
```

Local source:

```text
skills/battle/spectator/public/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json
```

Stream sidecars currently exist for future Phase 2 transport work:

```text
http://localhost:3002/battle-fixtures/battle-004-parent-spawn-pixi-replay/stream/manifest.json
http://localhost:3002/battle-fixtures/battle-004-parent-spawn-pixi-replay/stream/latest-snapshot.json
http://localhost:3002/battle-fixtures/battle-004-parent-spawn-pixi-replay/stream/events.jsonl
```

Phase 1 authority is still the normalized fixture JSON, not the stream.

Fresh Arena fixture coverage now also includes:

```text
http://localhost:3002/battle-fixtures/battle-005-ssrf-metadata-pixi-replay/battle.normalized_ux_fixture.json
http://localhost:3002/battle-fixtures/battle-006-pickle-deserialization-pixi-replay/battle.normalized_ux_fixture.json
http://localhost:3002/battle-fixtures/battle-007-file-upload-pixi-replay/battle.normalized_ux_fixture.json
```

## Backend Contract State

The current fixture contract is `battle.normalized_ux_fixture.v1`.

Important top-level fields now include:

```text
schema = battle.normalized_ux_fixture.v1
battle_id = battle-004
mocked = false
status = PASS
sprite_theme.schema = battle.sprite_theme.v1
```

The parent-spawn fixture currently exposes two sprite variants:

```text
crimson_hornbreaker
plague_nurgling
```

The fixture lanes now carry backend-selected actor visuals:

```text
lanes[].actor_visual.schema = battle.actor_visual.v1
lanes[].actor_visual.variant_id
lanes[].actor_visual.initial_state
lanes[].actor_visual.state_timeline[]
```

Verified lane assignments in the public fixture:

```text
payload-857-receipt -> crimson_hornbreaker
payload-857-red-1   -> plague_nurgling
```

The spectator resolver currently prefers:

```text
lane.actor_visual.variant_id -> fixture.sprite_theme.variants[variant_id].sprite_id
```

Hardcoded lane overrides remain only as design-fixture fallback for lanes that do not carry backend actor visuals.

Actor visual state is semantic, not Pixi-specific. The backend chooses `variant_id` and state names. The UX resolves those through `sprite_theme`; the backend must not emit Pixi frame indices, x/y pixels, easing, camera movement, or animation timing curves.

## Sprite State Contract

The backend emits sprite state transitions in:

```text
lanes[].actor_visual.state_timeline[]
```

Each transition has:

```text
at_seconds
state
source_event_id
source_receipt_id
segment_id, when available
provisional = false
```

Current states observed in the parent-spawn fixture include:

```text
research
payload
handoff
spawn
blocked
```

Terminal or outcome-implying states must be receipt-gated:

```text
blocked
killed
promoted
fastest_crash
victory
```

Current fixture proof scope explicitly says actor visuals are cosmetic identity only:

```text
cosmetic_identity_only = true
terminal_states_receipt_gated = true
```

This means sprite choice does not prove an Arena outcome. Judge/receipt events still own battle truth.

## Spawn Timing Rules

Child visibility is controlled by the lineage spawn receipt, not by client inference.

Authoritative source for child appearance:

```text
lineage.spawns[].visible_from_elapsed_seconds
lineage.spawns[].spawn_elapsed_seconds
```

Current public fixture values:

```text
parent lane: payload-857-receipt
child lane: payload-857-red-1
spawn_elapsed_seconds = 116.973449
visible_from_elapsed_seconds = 116.973449
first_active_segment_elapsed_seconds = 146.686852
child_start_elapsed_seconds = 146.686852
```

Interpretation:

```text
visible_from_elapsed_seconds:
  when the child lane may appear / materialize.

first_active_segment_elapsed_seconds:
  when the child first has active exploit work after materialization.
```

Do not hide the child until `first_active_segment_elapsed_seconds`. That field is not the spawn visibility gate.

Direct lane parent fields are now redundant with the lineage receipt in the current parent-spawn fixture:

```text
payload-857-red-1.parentId = payload-857-receipt
payload-857-red-1.parent_id = payload-857-receipt
```

UX should still treat `lineage.spawns[]` and `lineage.groups[]` as the authoritative relation and use lane parent fields as redundant render hints only.

## Exploit Lifecycle And Pressure Scoring Contract

The backend now exports deterministic contract artifacts for exploit scoring and lifecycle DAG behavior:

```bash
./run.sh export-semantic-outcome-matrix --out /tmp/battle-semantic-outcome-matrix.json
./run.sh validate-semantic-outcome-matrix /tmp/battle-semantic-outcome-matrix.json
./run.sh export-exploit-lifecycle-dag --out /tmp/battle-exploit-lifecycle-dag.json
./run.sh validate-exploit-lifecycle-dag /tmp/battle-exploit-lifecycle-dag.json
./run.sh validate-exploit-lifecycle-receipts /tmp/battle-004-live-first-lifecycle-20260707T221844/exploit-lifecycle-receipts.json
./run.sh export-exploit-lifecycle-receipts /tmp/battle-004-live-first-lifecycle-20260707T221844 --out /tmp/battle-004-live-first-lifecycle.receipts.export.json
```

Key policies:

```text
not_spawned_blue_block_scores_above_kill = true
confirmed_kill_requires_kill_receipt = true
suspected_pressure_does_not_count_as_blue_kill = true
preemptive_spawn_requires_suspected_pressure_not_confirmed_kill = true
pressure_signals_are_observations_not_authority = true
```

Subagents may suspect Blue pressure from observation signals such as stderr/stdout drift, response-body drift, timing shifts, probe failures, or explicit Blue/Judge receipts. Suspicion may justify a `strategic_pre_kill` spawn, but it must not become a confirmed Blue scan, kill, or block without corroborating Blue/Judge receipt evidence.

## Live Tau Exploit Lifecycle Receipt Slice

The first live-first lifecycle artifact now targets existing BATTLE-004 parent-spawn Zip Slip:

```bash
./run.sh arena-parent-spawn-proof battle-004 --out /tmp/battle-004-live-first-lifecycle-20260707T221844 --red-workers 2 --blue-workers 2
./run.sh validate-exploit-lifecycle-receipts /tmp/battle-004-live-first-lifecycle-20260707T221844/exploit-lifecycle-receipts.json
```

Live receipt bundle:

```text
/tmp/battle-004-live-first-lifecycle-20260707T221844/exploit-lifecycle-receipts.json
schema = battle.exploit_lifecycle_receipts.v1
mocked = false
live = true
proof_mode = live_tau
receipt_count = 17
pressure_receipt_count = 5
lineage_receipt_count = 1
spawn_decisions = [post_block_handoff]
outcome_classes = [post_spawn_child_contained, spawn_pressure_conceded]
```

Source-derived bug/learning from the live run:

```text
Existing BATTLE-004 parent-spawn path spawns after Judge BLUE_SUCCESS.
That means the current live path is post_block_handoff, not strategic_pre_kill survival.
It does not yet prove that an exploit predicted likely kill and replicated before confirmed death.
```

The lifecycle receipt validator enforces:

```text
drift-only pressure cannot claim confirmed Blue scan, block, or kill
confirmed kill requires a kill receipt
post_block_handoff requires parent_state = blocked
strategic_pre_kill / panic_spawn cannot follow an earlier confirmed kill receipt
```

## Playhead Authority

When `timeline_elapsed_axis_model.x_position_is_elapsed_time = true`, the playhead authority is:

```text
timeline_elapsed_axis_model.playhead.current_elapsed_seconds
```

The backend now mirrors that into:

```text
battle_timeline_control.playhead.current_seconds
battle_timeline_control.playhead.source = timeline_elapsed_axis_model.playhead.current_elapsed_seconds
battle_timeline_control.playhead.semantics = receipt_elapsed_axis_playhead
```

Current public fixture values:

```text
timeline_elapsed_axis_model.playhead.current_elapsed_seconds = 149.77601
battle_timeline_control.playhead.current_seconds = 149.77601
battle_timeline_control.playhead.legacy_clock_current_seconds = 110.502136
```

`legacy_clock_current_seconds` is retained for diagnosis only. UX should not drive elapsed-axis replay from it.

## Public Fixture Surface

Parent-spawn replay fixture:

```text
skills/battle/spectator/public/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json
```

Parent-spawn stream sidecars:

```text
skills/battle/spectator/public/battle-fixtures/battle-004-parent-spawn-pixi-replay/stream/manifest.json
skills/battle/spectator/public/battle-fixtures/battle-004-parent-spawn-pixi-replay/stream/latest-snapshot.json
skills/battle/spectator/public/battle-fixtures/battle-004-parent-spawn-pixi-replay/stream/events.jsonl
```

Sparse negative replay fixture:

```text
skills/battle/spectator/public/battle-fixtures/battle-004-sparse-pixi-replay/battle.normalized_ux_fixture.json
```

The sparse fixture is for negative/fail-closed checks. It should have lineage missing or zero spawn count and must not produce fake child density.

## Code Changed

Backend/schema files touched:

```text
skills/battle/src/battle_skill/battle_event_adapter.py
skills/battle/src/battle_skill/arena_live_battle_proof.py
skills/battle/src/battle_skill/cli.py
skills/battle/src/battle_skill/ux_contract_validator.py
skills/battle/schemas/battle.normalized_ux_fixture.v1.schema.json
skills/battle/schemas/battle.exploit_lifecycle_receipt.v1.schema.json
skills/battle/tests/test_arena_live_battle_proof_contract.py
```

Generated/data files touched:

```text
skills/battle/local/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json
skills/battle/local/battle-004-parent-spawn-pixi-replay/stream/latest-snapshot.json
skills/battle/local/battle-004-parent-spawn.normalized.json
skills/battle/local/battle-004-renderer-bundle.json
skills/battle/local/battle-004-sparse-pixi-replay/battle.normalized_ux_fixture.json
skills/battle/local/battle-004-sparse.normalized.json
skills/battle/local/battle-004-ux-data-contract-index.json
skills/battle/local/battle-004-ux-renderer-values.json
skills/battle/spectator/src/lib/battle-data.generated.ts
```

Public fixture files updated under:

```text
skills/battle/spectator/public/battle-fixtures/
```

## Verification Evidence

Recent backend-side checks run before this handoff:

```bash
cd skills/battle
./run.sh validate-ux-contract local/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json
./run.sh validate-ux-contract local/battle-004-sparse.normalized.json
./run.sh validate-ux-contract local/battle-004-sparse-pixi-replay/battle.normalized_ux_fixture.json
./run.sh validate-ux-renderer-values local/battle-004-ux-renderer-values.json
./run.sh validate-ux-data-contract-index local/battle-004-ux-data-contract-index.json
cd spectator
npm run typecheck
npm test
node scripts/prove-battle-sparse-negative.mjs
BATTLE_HOST=http://127.0.0.1:3002 ./run.sh prove-spectator
uv run pytest tests/test_battle_event_adapter_contract.py -q
uv run pytest tests/test_arena_live_battle_proof_contract.py -q
uv run python -m battle_skill.cli export-semantic-outcome-matrix --out /tmp/battle-semantic-outcome-matrix-pressure.json
uv run python -m battle_skill.cli validate-semantic-outcome-matrix /tmp/battle-semantic-outcome-matrix-pressure.json
uv run python -m battle_skill.cli export-exploit-lifecycle-dag --out /tmp/battle-exploit-lifecycle-dag-pressure.json
uv run python -m battle_skill.cli validate-exploit-lifecycle-dag /tmp/battle-exploit-lifecycle-dag-pressure.json
uv run python -m battle_skill.cli validate-exploit-lifecycle-receipts /tmp/battle-004-live-first-lifecycle-20260707T221844/exploit-lifecycle-receipts.json
```

Observed results from the prior run:

```text
Parent fixture validation: PASS
Sparse fixture validation: PASS
Renderer values/index validation: PASS
Spectator typecheck: PASS
Vitest: 44/44 tests in the full spectator gate
Sparse negative proof: PASS
BATTLE_PROVE_SPECTATOR_PASS
Battle event adapter contract tests: 98/98 tests
Arena live lifecycle receipt contract tests: 3/3 tests
Semantic outcome matrix export/validate: PASS, 8 outcome cases, 5 profile cases
Exploit lifecycle DAG export/validate: PASS, 10 nodes, 9 edges, 8 outcome classes
Live lifecycle receipts validate: PASS, 17 receipts, 5 pressure receipts, 1 lineage receipt, post_block_handoff
BATTLE_PROVE_BACKEND_GOAL_PASS after adding the live lifecycle receipt contract tests
```

Evidence classification:

```text
mocked: no for generated Battle fixture artifacts marked mocked=false
live: yes for local file/public route proof checks that exercised the spectator package
deterministic_contract: yes for semantic outcome matrix and exploit lifecycle DAG export/validate
live_tau_receipts: yes for BATTLE-004 parent-spawn lifecycle receipt bundle
```

Do not treat actor visual consumption as outcome proof. It proves sprite identity resolution only; Judge/receipt events still own block, kill, spawn, and score truth.

## Known Gaps / Do Not Infer

1. Hardcoded lane-to-sprite overrides remain only as fallback:

```text
skills/battle/spectator/src/engine/battle-lane-variant-map.ts
```

The expected primary resolver is:

```text
lane.actor_visual.variant_id -> fixture.sprite_theme.variants[variant_id]
```

2. The stream package is present but not Phase 1 authority. Do not make UX consume `events.jsonl` until fixture replay and actor visual resolution are stable.

3. Do not generate fake density. Child lanes require lineage receipt fields in `lineage.spawns[]`.

4. Do not show terminal effects from sprite states alone. Terminal effects require Judge/receipt-backed fixture events.

5. Fresh Arena runs exist for BATTLE-005, BATTLE-006, and BATTLE-007. The BATTLE-004 parent-spawn fixture remains generated from its existing receipt-backed parent-spawn artifact set.

6. Do not infer pre-kill survival from the current BATTLE-004 lifecycle receipt. It proves live receipt collection around a post-block handoff spawn only.

## Next Backend Actions

1. Add `exploit-combiner-proof` before the full genetic Battle engine.
2. Keep `lineage.spawns[]` as the fail-closed source even though lane parent fields are now redundant.
3. Continue broadening exploit classes when new scenario kinds are added; update `battle.semantic_outcome_matrix.v1` and `battle.exploit_lifecycle_dag.v1` together.
4. Do not make stream sidecars Phase 1 authority. Phase 2 stream consumption should validate `battle.transport_manifest.v1`, `battle.live_event.v1`, and `battle.snapshot.v1` against the normalized fixture first.
5. If UX adds stream playback, rerun `BATTLE_HOST=http://127.0.0.1:3002 ./run.sh prove-spectator` and inspect screenshots for BATTLE-004/005/006/007.
6. After the combiner rung is stable, change Tau/Battle spawn policy so Red can emit `strategic_pre_kill` or `panic_spawn` from suspected pressure before Judge BLUE_SUCCESS, then validate the resulting lifecycle receipts.

## Exploit Combiner Proof Rung

Next backend rung:

```text
./run.sh exploit-combiner-proof battle-004 --out /tmp/battle-004-combiner
```

Purpose:

```text
Prove the specimen lifecycle for nondeterministic exploit-code synthesis:
generated/bad code -> Docker run -> failure observations -> target contact ->
repaired/runnable specimen -> no exploit-success claim.
```

Current non-claims:

```text
The first proof is fixture-backed and agentic:false.
It does not prove Tau generated the code.
It does not prove exploit success.
Runnable specimen is not exploit success.
Target contact is not exploit success.
Child spawn materialization is future work.
Judge replay is required for exploit-success claims.
```

## Spawn Architect Proof Rung

Next backend rung after `exploit-combiner-proof`:

```text
./run.sh spawn-architect-proof battle-004 \
  --out /tmp/battle-004-spawn-architect \
  --parent-combiner-proof /tmp/battle-004-combiner
```

Purpose:

```text
Prove the DAG birth contract:
spawn-policy decision -> child knowledge packet -> tau.dag_contract.v1 child
exploit-synthesis DAG -> private-boundary validation -> no Tau execution.
```

Current non-claims:

```text
The proof is fixture-backed and agentic:false.
Tau execution is deferred to PR3.
It does not prove a child exploit subagent ran.
It does not prove a child exploit specimen was generated.
It does not prove any exploit code compiled or contacted the target.
It does not prove exploit success.
It does not prove Blue detection, kill, or block.
```

## Live Tau Child DAG Canary Rung

Next backend rung after `spawn-architect-proof`:

```text
./run.sh live-tau-child-dag-canary battle-004 \
  --out /tmp/battle-004-live-tau-child-dag \
  --spawn-architect-proof /tmp/battle-004-spawn-architect
```

Purpose:

```text
Attempt the existing local Tau runtime against the child DAG contract without
fixture fallback. Battle records tau-preflight-receipt.json, invokes
uv run tau dag-run, captures stdout/stderr, consumes Tau's dag-receipt.json
when present, and only runs a child specimen in Docker if Tau produces a
battle_exploit_runner_handoff.json and code artifact.
```

Current non-claims:

```text
This canary does not prove exploit success.
It does not prove Blue detection, child survival, or packet-level behavior.
Failure to invoke Tau is BLOCKED, not a passed fixture substitute.
Missing Tau receipts or child artifacts are BLOCKED.
Compile-repair exhaustion or missing Battle handoff is BLOCKED.
Private Arena references or exploit-success claims without Judge are FAIL.
```

## Next UX Agent Contract

The UX agent should consume:

```text
fixture.sprite_theme
lane.actor_visual.variant_id
lane.actor_visual.initial_state
lane.actor_visual.state_timeline[]
lineage.spawns[].visible_from_elapsed_seconds
timeline_elapsed_axis_model.playhead.current_elapsed_seconds
```

The UX agent should not consume:

```text
legacy_clock_current_seconds for elapsed-axis replay
hardcoded lane -> sprite overrides as source of truth
first_active_segment_elapsed_seconds as child visibility gate
stream/events.jsonl as Phase 1 authority
```

## Working Tree Status At Handoff

Battle-local changes are currently uncommitted.

Relevant `git status --short skills/battle` entries:

```text
M skills/battle/local/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json
M skills/battle/local/battle-004-parent-spawn-pixi-replay/stream/latest-snapshot.json
M skills/battle/local/battle-004-parent-spawn.normalized.json
M skills/battle/local/battle-004-renderer-bundle.json
M skills/battle/local/battle-004-sparse-pixi-replay/battle.normalized_ux_fixture.json
M skills/battle/local/battle-004-sparse.normalized.json
M skills/battle/local/battle-004-ux-data-contract-index.json
M skills/battle/local/battle-004-ux-renderer-values.json
M skills/battle/schemas/battle.normalized_ux_fixture.v1.schema.json
M skills/battle/spectator/src/lib/battle-data.generated.ts
M skills/battle/src/battle_skill/battle_event_adapter.py
M skills/battle/src/battle_skill/ux_contract_validator.py
```

This handoff file is also uncommitted after creation.
