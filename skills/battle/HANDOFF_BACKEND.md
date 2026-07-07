# Battle Backend Handoff

Timestamp: 2026-07-07T16:08:46-04:00
Authoring agent: Codex
Scope: BATTLE backend/schema/fixture contract only. UX layout and Pixi rendering implementation are owned by the UX project agent.

## Current Objective

Provide a backend-generated BATTLE-004 Arena fixture that the Pixi spectator UX can replay without inventing client-side battle truth.

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

Known caveat: direct lane parent fields are not yet redundant enough. The child lane currently has `parent_id = null` in the public fixture query, while `lineage.spawns[]` and `lineage.groups[]` correctly define the parent-child relationship. UX should use `lineage.spawns[]` and `lineage.groups[]` as the authoritative relation for Phase 1.

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
skills/battle/src/battle_skill/ux_contract_validator.py
skills/battle/schemas/battle.normalized_ux_fixture.v1.schema.json
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
```

Observed results from the prior run:

```text
Parent fixture validation: PASS
Sparse fixture validation: PASS
Renderer values/index validation: PASS
Spectator typecheck: PASS
Vitest: 20/20 tests
Sparse negative proof: PASS
```

Evidence classification:

```text
mocked: no for generated BATTLE fixture artifacts marked mocked=false
live: yes for local file/public route proof checks that exercised the spectator package
not yet verified: UX consumption of actor_visual.variant_id replacing hardcoded lane overrides
```

Do not treat the above as proof that the Pixi renderer has already consumed `actor_visual`. It proves the backend generated and validated the contract fields.

## Known Gaps / Do Not Infer

1. The UX may still use a hardcoded lane-to-sprite map such as:

```text
skills/battle/spectator/src/engine/battle-lane-variant-map.ts
```

The next UX step is to replace hardcoded lane overrides with:

```text
lane.actor_visual.variant_id -> fixture.sprite_theme.variants[variant_id]
```

2. The stream package is present but not Phase 1 authority. Do not make UX consume `events.jsonl` until fixture replay and actor visual resolution are stable.

3. Do not generate fake density. Child lanes require lineage receipt fields in `lineage.spawns[]`.

4. Do not show terminal effects from sprite states alone. Terminal effects require Judge/receipt-backed fixture events.

5. No new Arena run was created for this handoff. The current parent-spawn fixture is generated from the existing receipt-backed BATTLE-004 parent spawn artifact set.

## Next Backend Actions

1. Add redundant lane parent fields so `lanes[]` also agrees with `lineage.spawns[]`:

```text
payload-857-red-1.parent_id = payload-857-receipt
```

2. Keep `lineage.spawns[]` as the fail-closed source even after redundant lane fields are added.

3. Regenerate fixture artifacts after the lane parent field fix:

```bash
cd skills/battle
./run.sh generate-ux-fixture --input /tmp/battle-004-parent-spawn-20260706T134722Z --battle-id battle-004 --out local/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json --ts-out spectator/src/lib/battle-data.generated.ts
./run.sh validate-ux-contract local/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json
```

4. Re-export renderer/index artifacts and update public fixture copies.

5. After UX switches to actor visual resolution, run the receipt replay proof against `http://localhost:3002/#battle/receipt?engine=pixi`.

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
