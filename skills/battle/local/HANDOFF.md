# Handoff Report: Battle

**Timestamp**: 2026-07-05T12:35:00Z  
**Active Agent**: Codex  
**Primary Machine Contract**: `local/battle-004-ux-json-contract-summary.json`

## 1. Project Overview

- **Ecosystem**: Python Battle skill producing receipt-backed JSON for the
  self-contained React spectator package at `skills/battle/spectator/`.
  `ux-lab` is a thin host only.
- **Core Purpose**: Run and display Red/Blue Battle proof artifacts for
  canonical BATTLE-004: `POST /api/import-zip`, `CWE-22`, Zip Slip.

## 2. Current State

- **Implemented Reality**: Bounded Tau worker-matrix rung plus Judge replay.
  Parent-spawn lineage rung is wired in code, demonstrated by a fresh live
  receipt artifact, and guarded by adapter/UX-contract validation.
- **Important Gap**: Live lineage only materializes when parent Red lane gets
  `BLUE_SUCCESS` and Tau child spawn succeeds. Sparse proofs stay sparse.
- **Agent Boundary**: Battle backend agents own proof receipts, normalized JSON,
  schema validation, timing/playhead values, lane cockpit values, replay metadata,
  spectator-shell values, and fail-closed guards. They do not own React layout,
  mockup parity, visual design, or CDP screenshot acceptance.


## Pixi Phase 1 spike (spectator package)

Optional Pixi race renderer behind `#battle?engine=pixi` and `#battle/receipt?engine=pixi`. Default remains DOM/SVG. Implementation lives in `skills/battle/spectator/`.

- **Spectator package (canonical UI):** `skills/battle/spectator/`
- **Contract:** `skills/battle/docs/BATTLE_RACE_ENGINE_PIXI_SPIKE.md`
- **Backend:** renderer-neutral — see `BACKEND_UX_CONTRACT.md`
- **Agent skills:** official `pixijs*` + `best-practices-battle-pixi` overlay
- **Sprite sheets:** not required for Phase 1 (procedural Graphics); see spike doc § Asset pipeline

## 3. What Is Working

- `battle_event_adapter.py` reads `lineage-receipts.json`, emits child lanes,
  parent `children[]`, `tau.spawned_child` events, and updates claims when
  lineage is valid.
- `arena_live_battle_proof.py` runs parent-first Tau matrix, Judge, then optional
  child spawn via Tau `--spawn-red-child` when parent is blocked.
- `tau_coding/battle_live_handoff.py` supports spawned Red child receipts and
  per-spawn lineage artifacts under `tau-live/lineage/`.
- Standalone HTML mockup baseline lives at
  `mockups/battle-004-shell-preserving-scroll-timeline.html`.
- Machine-readable UX handoff lives at
  `local/battle-004-ux-json-contract-summary.json`; UI agents should consume
  those JSON paths and values instead of asking Battle to design the interface.
- The current authoritative parent-spawn fixture is
  `local/battle-004-parent-spawn.normalized.json`, sourced from live proof
  `/tmp/battle-004-parent-spawn-live-timing-20260705T125418Z`.

## 4. What Is Broken / Unverified

- React mechanical render + CDP screenshot gate is out of scope for the Battle
  backend agent under the current human instruction. The UX renderer should
  consume the normalized JSON contract and run its own visual gates.
- `sanity.sh` now runs through normalized UX validation after moving the
  generated root `.venv` to storage and replacing it with a symlink to
  `/mnt/storage12tb/skills/battle/.venv`. The preserved backup is under
  `/mnt/storage12tb/skills/battle/.venv-worktree-backup-*`.
- Some live runs still return `INSUFFICIENT_EVIDENCE`; those are expected to
  stay sparse and must not render child lineage.
- Timeline x positions are currently receipt-order percentages, not elapsed
  seconds. This is explicit in `timeline_time_model.x_position_is_elapsed_time`
  and must stay visible to renderers until Battle emits per-step elapsed
  timestamps. The playhead is receipt replay only, not a live timer.
- The active `/goal` text still mentions React UI ownership; treat that as stale
  relative to the latest human scope boundary until the human explicitly changes
  ownership again.

## 5. Next Steps

1. Use the latest receipt-backed parent-spawn proof for backend JSON:

```text
/tmp/battle-004-parent-spawn-live-timing-20260705T125418Z
```

2. Re-run canonical proof when a fresh artifact is needed:

```bash
cd /home/graham/workspace/experiments/agent-skills/skills/battle
./run.sh arena-parent-spawn-proof battle-004 \
  --red-workers 2 \
  --blue-workers 2 \
  --out <fresh-proof-dir>
```

This command requests one parent Red lane first, Judge-replays the parent/Blue
pairs, and only asks Tau for the child Red lane after the parent has a
`BLUE_SUCCESS` handoff. The resulting child is a receipt-backed lineage result,
not a UI-density signal.

3. Confirm proof dir contains `run-receipt.json#lineage_request` and, when
   successful, `lineage-receipts.json` with `status: PASS` and
   child lane `payload-857-red-1` only when parent lane was `BLUE_SUCCESS`.

4. Regenerate UX fixture:

```bash
./run.sh generate-ux-fixture \
  --input <fresh-proof-dir> \
  --battle-id battle-004 \
  --out /tmp/battle-004.normalized.json
```

5. Validate the backend UX contract before handing data to any renderer:

```bash
./run.sh validate-ux-contract /tmp/battle-004.normalized.json
```

For the checked-in local handoff bundle, use the whole-bundle gate:

```bash
./run.sh validate-ux-handoff-summary local/battle-004-ux-json-contract-summary.json
```

6. UI renderer must use JSON-owned values:

- `spectator_shell` for header title, subtitle, fact chips, score labels/values,
  round-time text, mode/truth labels, and receipt event ticker text.
- `battle_clock` for allotted/elapsed/remaining time.
- `timeline.playhead` and `timeline.keyframes` for receipt replay state.
- `timeline_time_model` to distinguish receipt-order x positions from real
  elapsed-time placement.
- `timeline.viewport`, `timeline.supports_pan`, and `timeline.supports_zoom`
  for scroll/zoom behavior.
- `lineage_request` for requested/not-requested/proven child-spawn state. This
  field explains intent only; it must not create child lanes unless
  `lineage.spawns[]` also contains receipt-backed spawn records.
- `lineage.groups[]`, lane `children[]`, `parentId`, `collapsible`, and
  `expandedByDefault` for parent/child collapse.
- lane `activitySegments[]` for between-marker action labels.
- lane `cockpit.selected_tau_exploit_subagent` for Agent Detail Tau identity.
- lane `cockpit.current_turn`, `cockpit.public_trace`, `cockpit.output.stdout`,
  `cockpit.output.stderr`, `cockpit.skills_tools`, `cockpit.blue_outcome`, and
  `cockpit.latest_receipt_id` for selected-lane details.
- lane `replay.cta` for Docker replay button state.

7. Machine-readable renderer binding paths live in:

```text
local/battle-004-ux-json-contract-summary.json#renderer_binding_contract
```

Those bindings are the contract for shell text, round time, scrollable timeline,
moving playhead, parent spawn/collapse, lane labels, Agent Detail cockpit, and
Docker replay CTA state.

## 6. Key Files

- `GOAL.md`
- `docs/BATTLE_004_DESIGN_HANDOFF.md`
- `mockups/battle-004-shell-preserving-scroll-timeline.html`
- `src/battle_skill/arena_live_battle_proof.py`
- `src/battle_skill/battle_event_adapter.py`
- `src/battle_skill/cli.py`
- `/home/graham/workspace/experiments/tau/src/tau_coding/battle_live_handoff.py`
- `skills/battle/spectator/src/` (ux-lab mounts via `@agent-skills/battle-spectator`)

## 7. Verification Performed This Session

| Check | mocked | live | Result |
|---|---|---|---|
| `py_compile` battle adapter/arena/cli | no | yes | PASS |
| Parent-spawn proof `/tmp/battle-004-parent-spawn-live-timing-20260705T125418Z` | no | yes | PASS (`child_spawn_count=1`, `tau.spawned_child`) |
| Adapter + arena contract tests | mixed fixture/control-plane tests | local fixture | PASS (`92 passed`) |
| `validate-ux-contract` parent-spawn and sparse artifacts | no | yes for parent-spawn source artifact | PASS |
| renderer bundle/value/index/handoff validators | no | local receipt-backed fixtures | PASS |
| `python3 scripts/check_mock_evidence_claims.py` | no | local source scan | PASS |
| `./sanity.sh` | no | local fixture + UX fixture | PASS (`Result: PASS`) |

## 8. Operating Rule

The Battle project agent owns internals, evidence, and JSON values. External UI
implementation owns visual direction and CDP acceptance. Dense UX must come from
dense receipts, not UI-invented density.

## Docs
- Interface spec: `docs/BATTLE_004_INTERFACE_IMPLEMENTATION_SPEC.md`
- Receipt truth handoff: `docs/BATTLE_004_DESIGN_HANDOFF.md` (renamed scope; filename unchanged)
