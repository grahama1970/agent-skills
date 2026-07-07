# BATTLE-004 Parent-Spawn Pixi Replay Example

Purpose: stable backend-owned replay input for the `#battle` PixiJS UX.

This example is copied from receipt-backed proof:

`/tmp/battle-004-parent-spawn-20260706T134722Z`

## UX Entry Points

- Snapshot: `stream/latest-snapshot.json`
- Append-only stream: `stream/events.jsonl`
- Transport manifest: `stream/manifest.json`
- Normalized fixture: `battle.normalized_ux_fixture.json`

## Source Receipts

- `proof/run-receipt.json`
- `proof/scoreboard.json`
- `proof/lineage-receipts.json`
- `proof/tau-live-manifest.json`

## Required UX Behavior

- Render one parent Red lane.
- Render one child Red lane only after the `tau.spawned_child` event.
- Use `timeline_elapsed_axis_model.playhead.current_elapsed_seconds` as the receipt replay playhead when `x_position_is_elapsed_time=true`.
- Treat `battle_timeline_control.playhead.current_seconds` as synchronized compatibility metadata.
- Use `lineage.spawns[].visible_from_elapsed_seconds` / `spawn_elapsed_seconds` for child lane visibility.
- Use `lineage.spawns[].first_active_segment_elapsed_seconds` / `child_start_elapsed_seconds` for the first active child segment.
- Use `segments[]` for runner interpolation.
- Do not draw lane progress before each lane start.
- Do not invent fastest crash, killed, promotion, or Blue kill states.
- Pixi owns sprite frames, canvas coordinates, easing, particles, camera, zoom, and scroll.

## Expected Counts

- `stream/events.jsonl`: 24 events
- `tau.spawned_child`: 1 event
- `battle.segment_declared`: 12 events
- `lanes[]`: 2 lanes
- `lineage.spawn_count`: 1

## Verification

From the repo root:

```bash
cd skills/battle
./run.sh validate-ux-contract local/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json
```

The expected result includes:

```json
{
  "status": "PASS",
  "lineage_mode": "receipt_backed",
  "child_spawn_count": 1,
  "mocked": false,
  "live_source": "brave_search_docker_arena_oracle_tau_harness"
}
```
