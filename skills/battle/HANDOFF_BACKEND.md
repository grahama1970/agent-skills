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

Current PR3a command-spec target:

```text
Spawn Architect materializes command-specs/child-exploit-dag/*/tau-dispatch-command.json
beside child-exploit-dag.yaml. Tau should compile those specs and invoke
battle_skill.child_dag_node_adapter through the real local command loop.

The first expected non-fixture result is:
lineage-summarizer PASS -> research-scout BLOCKED because no real
source-bearing research adapter is configured. That is progress over
MISSING_AGENT_COMMAND_SPEC, but still not live child exploit synthesis.
```

Current PR3b command-spec target:

```text
lineage-summarizer PASS
research-scout PASS
method-combiner PASS
exploit-code-author BLOCKED
```

`research-scout` must produce:

```text
research-source-packet.json
research-source-receipt.json
research_receipts.json
candidate_methods.json
research-scout-node-receipt.json
```

The source receipt is Tau-owned:

```text
schema = tau.research_source_receipt.v1
status = PASS
review_required = true
```

`method-combiner` must produce:

```text
exploit_genome.json
combination_rationale.md
method-combiner-node-receipt.json
```

PR3b claim boundary:

```text
research citations are design input, not proof
exploit_genome.json is not exploit code
fixture child code fallback is forbidden
exploit-code-author remains BLOCKED until a real Tau/provider code-authoring adapter exists
Judge remains the only authority for exploit success
```

Current PR3c provider-authorship target:

```text
lineage-summarizer PASS
research-scout PASS
method-combiner PASS
exploit-code-author PASS only with provider_live:true attestation
compile-repair may remain BLOCKED
```

`exploit-code-author` now writes a bounded provider workspace and receipts:

```text
exploit-code-author/inputs/exploit-code-author-work-order.json
exploit-code-author/inputs/tau-scillm-worker-work-order.json
exploit-code-author/receipts/workspace-baseline-manifest.json
exploit-code-author/receipts/tau-scillm-worker-launch-receipt.json
exploit-code-author/receipts/provider-artifact-validation.json
exploit-code-author/receipts/provider-authorship-receipt.json
exploit-code-author/receipts/provider-code-author-boundary-receipt.json
```

Phase 1 PR3c PASS requires:

```text
provider_live = true
agentic = true
fixture_fallback_used = false
provider run/session evidence
work-order and code hash binding
provider-authored exploit_specimen.py under outputs/
compile_status = NOT_RUN
runtime_status = NOT_RUN
judge_verified_exploits = 0
```

If Tau/SciLLM still reports `provider_live:false`, the correct backend result is
`PROVIDER_EXECUTION_ATTESTATION_MISSING`, not a frontend fixture or a fake child
specimen.

Normalized proof-card fixture:

```text
schema = battle.normalized_proof_card_fixture.v1
local path = skills/battle/local/battle-004-pr3b-proof-card/battle.normalized_proof_card_fixture.json
public URL = /battle-fixtures/battle-004-pr3b-proof-card/battle.normalized_proof_card_fixture.json
```

Generation and validation:

```bash
./run.sh normalize-proof-card-fixture /tmp/battle-pr3b-live-research-final/live-tau \
  --out local/battle-004-pr3b-proof-card/battle.normalized_proof_card_fixture.json
./run.sh validate-proof-card-fixture local/battle-004-pr3b-proof-card/battle.normalized_proof_card_fixture.json
```

UX must consume the normalized proof-card fixture only. Do not bind React to
Tau runtime directories such as `tau-dag-run/command-loop/command-artifacts`.

Normalized synthesis fixture:

```text
schema = battle.normalized_synthesis_fixture.v1
fixture kind = pr3c_provider_code_author
local path = skills/battle/local/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json
public URL = /battle-fixtures/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json
```

Generation and validation:

```bash
./run.sh normalize-synthesis-fixture /tmp/battle-pr3d-compile-repair-check/live-tau \
  --out local/battle-004-pr3c-synthesis \
  --public-out spectator/public/battle-fixtures/battle-004-pr3c-synthesis \
  --generated-at 2026-07-10T18:00:00Z
./run.sh validate-synthesis-fixture local/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json
./run.sh validate-synthesis-fixture spectator/public/battle-fixtures/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json
```

UX3 should consume the normalized synthesis fixture only. It may show:

```text
Provider authorship: PROVEN
Code artifact: MATERIALIZED
Compilation: NOT RUN
Runtime: NOT RUN
Target contact: NOT RUN
Judge: NOT RUN
Exploit success: NOT PROVEN
```

UX3 must not show compile pass, runnable child, target contact, exploit success,
Blue detection/block, packet-level behavior, or memory promotion from this PR3c
fixture. Do not bind React to raw Tau, command-loop, provider workspace, worker
result, or provider transcript paths.

Normalized compile fixture:

```text
schema = battle.normalized_compile_fixture.v1
fixture kind = pr3d_compile_repair
local path = skills/battle/local/battle-004-pr3d-compile/battle.normalized_compile_fixture.json
public URL = /battle-fixtures/battle-004-pr3d-compile/battle.normalized_compile_fixture.json
route = #battle/compile?fixture=battle-004-pr3d
```

Generation and validation:

```bash
./run.sh normalize-compile-fixture /tmp/battle-pr3d-compile-repair-check/live-tau \
  --out local/battle-004-pr3d-compile \
  --public-out spectator/public/battle-fixtures/battle-004-pr3d-compile \
  --generated-at 2026-07-10T19:00:00Z
./run.sh validate-compile-fixture local/battle-004-pr3d-compile/battle.normalized_compile_fixture.json
./run.sh validate-compile-fixture spectator/public/battle-fixtures/battle-004-pr3d-compile/battle.normalized_compile_fixture.json
```

UX4 should consume the normalized compile fixture only. It may show:

```text
Provider-authored specimen: EXISTS
Specimen versions: HASHED
Compile attempt: RECORDED
Compile failed or passed: RECEIPT-BACKED
Repair attempted/exhausted: EXPLICIT BOOLEAN FIELDS
Runtime: NOT RUN
Target contact: NOT RUN
Judge: NOT RUN
Exploit success: NOT PROVEN
```

Renderer field mapping:

```text
version timeline = specimen_versions[]
stderr panel = compile.stderr_summary
selected version = selected_version
repair status = repair.repair_attempted / repair.repair_exhausted
claim banner = claim_boundary
```

UX4 must not show runnable child, runtime success, target contact, exploit
success, Blue detection/block, packet-level behavior, Judge success, or memory
promotion from this PR3d fixture. Compile pass must not be rendered as runnable.
Do not bind React to raw Tau, command-loop, provider workspace, SciLLM/OpenCode
runtime directories, raw compile stderr paths, or worker result paths.

Normalized runtime/Judge fixture:

```text
schema = battle.normalized_runtime_judge_fixture.v1
fixture kind = pr4_runtime_judge
local path = skills/battle/local/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json
public URL = /battle-fixtures/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json
route = #battle/runtime?fixture=battle-004-pr4
```

Generation and validation:

```bash
./run.sh normalize-runtime-judge-fixture /tmp/battle-pr3d-compile-repair-check/combiner \
  --out local/battle-004-pr4-runtime-judge \
  --public-out spectator/public/battle-fixtures/battle-004-pr4-runtime-judge \
  --generated-at 2026-07-10T20:30:00Z
./run.sh validate-runtime-judge-fixture local/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json
./run.sh validate-runtime-judge-fixture spectator/public/battle-fixtures/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json
```

UX5 should consume the normalized runtime/Judge fixture only. It may show:

```text
Docker image/network/timeout: RECORDED
Specimen exit codes: RECORDED
stdout/stderr summaries: REDACTED SUMMARIES
Runtime failed / runnable unproven / target contact unproven: RECEIPT-BACKED
Judge progression: NOT_RUN
Judge verified exploits: 0
Exploit success: NOT PROVEN
```

Renderer field mapping:

```text
Docker policy = runtime.docker
runtime cards = runtime.specimen_runs[]
runtime totals = runtime.summary
Judge progression = judge.judge_progression / judge.judge_status
claim banner = claim_boundary
```

UX5 must not show exploit success, Blue detection/block, packet-level behavior,
Judge success, or memory promotion from this PR4 fixture. Target contact must be
rendered as `TARGET_CONTACT_UNPROVEN`, not as exploit proof. Do not bind React
to raw specimen directories, raw stdout/stderr paths, Docker mount paths,
Tau/command-loop directories, provider workspaces, or worker result paths.

## UX6 Population Fixture Handoff

Normalized population fixture:

```text
schema = battle.normalized_population_fixture.v1
fixture kind = pr5_population
local path = skills/battle/local/battle-004-pr5-population/battle.normalized_population_fixture.json
public URL = /battle-fixtures/battle-004-pr5-population/battle.normalized_population_fixture.json
route = #battle/population?fixture=battle-004-pr5-population
```

Generation and validation:

```bash
./run.sh normalize-population-fixture /tmp/battle-pr3d-compile-repair-check/combiner \
  --out local/battle-004-pr5-population \
  --public-out spectator/public/battle-fixtures/battle-004-pr5-population \
  --generated-at 2026-07-10T21:00:00Z
./run.sh validate-population-fixture local/battle-004-pr5-population/battle.normalized_population_fixture.json
./run.sh validate-population-fixture spectator/public/battle-fixtures/battle-004-pr5-population/battle.normalized_population_fixture.json
```

UX6 should consume the normalized population fixture only. It may show:

```text
specimen cards: specimen_cards[]
lineage tree: lineage_edges[]
generation scrubber: generation_axis
fitness and novelty: specimen_cards[].fitness / specimen_cards[].novelty
selection labels: specimen_cards[].selection
claim banner: claim_boundary
```

This fixture is generated from real local combiner specimen receipts and
contains four specimens across four generations with three receipt-backed
parent-child lineage edges. It is a bounded population fixture, not a claim that
the full autonomous genetic population engine exists.

UX6 must not show exploit success, provider-authored specimen claims, live Tau
code generation, Blue detection/block, packet-level behavior, Judge success, or
memory promotion from this PR5 fixture. Target contact must remain
`TARGET_CONTACT_UNPROVEN`, not exploit proof. Do not bind React to raw combiner
specimen directories, raw stdout/stderr paths, Docker mount paths,
Tau/command-loop directories, provider workspaces, or worker result paths.

## UX7 Genetic Pixi Fixture Handoff

Normalized genetic Pixi replay fixture:

```text
schema = battle.normalized_ux_fixture.v1
genetic_lifecycle.schema = battle.genetic_lifecycle_events.v1
local path = skills/battle/local/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json
public URL = /battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json
route = #battle/receipt?engine=pixi&fixture=battle-004-pr6-genetic-pixi
```

Generation and validation:

```bash
./run.sh normalize-genetic-pixi-fixture . \
  --out local/battle-004-pr6-genetic-pixi \
  --public-out spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi \
  --generated-at 2026-07-10T22:20:00Z
./run.sh validate-genetic-pixi-fixture local/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json
./run.sh validate-genetic-pixi-fixture spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json
./run.sh validate-ux-contract local/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json
./run.sh validate-ux-contract spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json
```

UX7 should consume only the normalized fixture. Do not read Tau runtime,
command-loop, provider workspace, raw combiner, Docker mount, raw stdout/stderr,
or Judge-internal paths.

Renderer field mapping:

```text
route = genetic_lifecycle.route
fixture URL = genetic_lifecycle.fixture_url
event vocabulary = genetic_lifecycle.required_event_types
present events = genetic_lifecycle.present_event_types
not emitted = genetic_lifecycle.not_emitted_event_types / not_emitted_reasons
lane id = events[].payload.lane_id
specimen id = events[].payload.specimen_id
method id = events[].payload.method_id
receipt id = events[].payload.receipt_id / events[].evidence.receipt_id
playhead placement = events[].elapsed_seconds / events[].payload.playhead_x
claim banner = genetic_lifecycle.claim_boundary
```

Currently emitted events:

```text
research_started
research_receipt_materialized
genome_selected
method_added
method_rejected
code_author_started
specimen_materialized
compile_failed
compile_passed
target_contact_unproven
judge_pending
branch_abandoned
```

Currently NOT_EMITTED:

```text
repair_started
repair_materialized
judge_exploit_success
genome_promoted
```

UX7 must not render victory, kill, containment, exploit success, Blue outcome,
packet behavior, or memory promotion unless a matching normalized event and
receipt exist. Compile pass is not runnable proof. Target contact is not exploit
proof. `judge_pending` in this fixture means Judge success is not emitted and
`judge_verified_exploits` remains `0`.

## UX8 Live Transport Contract Handoff

Normalized live transport contract:

```text
schema = battle.live_transport_contract.v1
local path = skills/battle/local/battle-004-pr8-live-transport/battle.live_transport_contract.json
public URL = /battle-fixtures/battle-004-pr8-live-transport/battle.live_transport_contract.json
route = #battle/live?engine=pixi&battle=battle-004
snapshot endpoint = /battle/live/battle-004/snapshot
SSE endpoint = /battle/live/battle-004/events
event schema = battle.live_event.v1
snapshot schema = battle.snapshot.v1
```

Generation and validation:

```bash
./run.sh publish-live-transport-contract \
  --out local/battle-004-pr8-live-transport \
  --public-out spectator/public/battle-fixtures/battle-004-pr8-live-transport \
  --generated-at 2026-07-11T01:30:00Z
./run.sh validate-live-transport-contract local/battle-004-pr8-live-transport/battle.live_transport_contract.json
./run.sh validate-live-transport-contract spectator/public/battle-fixtures/battle-004-pr8-live-transport/battle.live_transport_contract.json
```

UX8 should consume only this backend-published contract when implementing the
SSE client. Do not read Tau runtime, command-loop, provider workspace, raw
combiner, Docker mount, raw stdout/stderr, or Judge-internal paths.

Renderer/client field mapping:

```text
route = frontend_handoff.route
snapshot endpoint = initial_snapshot.endpoint
snapshot schema = initial_snapshot.schema
SSE endpoint = event_stream.endpoint
SSE content type = event_stream.content_type
event schema = event_stream.event_schema
sequence field = event_stream.ordering.seq_field
event id field = event_stream.ordering.event_id_field
receipt reference field = event_stream.ordering.receipt_ref_field
reconnect header = reconnect.header
resume field = reconnect.resume_from
gap policy = gap_semantics.on_gap
expected gap behavior = gap_semantics.client_action
genetic event vocabulary = frontend_handoff.genetic_event_types
claim banner = claim_boundary
```

This is a contract-only backend handoff:

```text
live = contract_only
mocked = false
may claim = backend live transport contract published, endpoint shape defined,
  ordering/reconnect/gap semantics defined, raw path boundary defined
must not claim = SSE endpoint implemented, WebSocket endpoint implemented,
  live stream executed, live genetic events emitted, exploit success,
  Blue detection/kill/block, Judge success without Judge receipt,
  packet-level behavior, memory promotion
```

The next backend slice, if frontend needs an executable live proof, is the
actual SSE server/adapter that emits `battle.snapshot.v1` and ordered
`battle.live_event.v1` records using this contract.

## UX8 Executable SSE Adapter Handoff

Executable local adapter:

```bash
./run.sh serve-live-transport \
  --fixture spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json \
  --battle-id battle-004 \
  --host 127.0.0.1 \
  --port 8765
```

Endpoints:

```text
GET /battle/live/battle-004/snapshot -> battle.snapshot.v1
GET /battle/live/battle-004/events -> text/event-stream of battle.live_event.v1
Last-Event-ID: <seq> resumes from the next event
Future Last-Event-ID beyond snapshot.last_seq fails closed with HTTP 400
```

Proof:

```bash
./run.sh prove-live-transport-server --out local/battle-004-pr8-live-transport-server-proof
```

Receipt:

```text
skills/battle/local/battle-004-pr8-live-transport-server-proof/live-transport-server-proof.json
```

Current proof receipt records:

```text
status = PASS
mocked = false
live = local_http_sse_adapter
snapshot_schema = battle.snapshot.v1
event_schema = battle.live_event.v1
event_count = 36
last_seq = 36
resume_from_last_event_id = 2
resumed_event_count = 34
future_last_event_id_status = 400
raw_paths_leaked = false
```

The adapter uses the normalized fixture as authority and must not read
`tau-dag-run/**`, `command-loop/command-artifacts/**`, provider workspace,
Docker mount, raw stdout/stderr, or Judge-internal paths. It proves local
HTTP/SSE execution only. It does not prove production deployment, WebSocket
support, exploit success, Blue detection/kill/block, Judge exploit success,
packet-level behavior, or memory promotion.

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

## Current Backend Handoff State

The active UX3 backend handoff is the PR3c normalized synthesis fixture:

```text
skills/battle/local/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json
skills/battle/spectator/public/battle-fixtures/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json
```

Those fixtures are generated from a live PR3c code-author boundary run and are
validated by `./run.sh validate-synthesis-fixture`. They intentionally stop at
provider-authored specimen materialization and keep compile, runtime, target
contact, Judge, Blue, packet, and memory states as `NOT_RUN` / not claimed.

The active UX4 backend handoff is the PR3d normalized compile fixture:

```text
skills/battle/local/battle-004-pr3d-compile/battle.normalized_compile_fixture.json
skills/battle/spectator/public/battle-fixtures/battle-004-pr3d-compile/battle.normalized_compile_fixture.json
```

Those fixtures are generated from a live PR3d compile-repair boundary run and
validated by `./run.sh validate-compile-fixture`. They intentionally stop at
compiler evidence and keep runtime, target contact, Judge, Blue, packet, and
memory states as `NOT_RUN` / not claimed.

The active UX5 backend handoff is the PR4 normalized runtime/Judge fixture:

```text
skills/battle/local/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json
skills/battle/spectator/public/battle-fixtures/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json
```

Those fixtures are generated from real local Docker specimen run receipts and
validated by `./run.sh validate-runtime-judge-fixture`. Judge remains
`NOT_RUN`; runtime target contact remains `TARGET_CONTACT_UNPROVEN`; no exploit,
Blue, packet, or memory outcome is claimed.
## Music M1 Spectator Handoff

Schema: `battle.normalized_music_fixture.v1`

Fixture ID: `battle-004-music-runtime`

Public URL:

```text
/battle-fixtures/battle-004-music-runtime/battle.normalized_music_fixture.json
```

Suggested route:

```text
#battle/music?fixture=battle-004-music-runtime
```

Field map:

```text
schedule entries: schedule.entries
promotion summaries and immutable hashes: promotions
receipt authorization: schedule.entries[].authorization
browser OGG and source MIDI: schedule.entries[].asset_ref
presentation limits: claim_boundary
unsupported cues: events_not_emitted
```

Only entries with `playback_class: promoted` are authoritative. Actor-focus
motifs remain `local_preview` behavior outside this schedule. The fixture does
not expose composer, create-midi, Tau, provider, or host working paths. It does
not prove browser playback, speaker output, live composer execution, death,
victory, arena transition, exploit success, Blue outcome, or Judge success.
