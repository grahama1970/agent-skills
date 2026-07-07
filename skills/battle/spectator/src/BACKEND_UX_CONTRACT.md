# BATTLE-004 Backend / UX Contract

| Field | Value |
|-------|-------|
| **Version** | 1.1 (2026-07-06) |
| **Status** | Authoritative for live backend integration |
| **Companion** | `DESIGN.md` (pixels/layout), `BATTLE_004_DESIGN_HANDOFF.md` (receipt adapter), `BATTLE_RACE_ENGINE_PIXI_SPIKE.md` (Pixi Phase 1 — UI only; backend stays renderer-neutral) |

## Authority split

```text
Backend owns:  clock, at_seconds, receipts, semantic events, lane derivation, Judge truth, render guards
UI owns:       pixels, x positions, zoom, scrollLeft, easing, CSS animation, layout thresholds
```


## Renderer neutrality

The backend contract is **renderer-neutral**.

The backend must not know whether the UI uses DOM/SVG, Pixi, Canvas, or another engine.

**Backend emits:**

- clock
- timeline_control
- semantic events
- segments
- lanes
- receipts
- provenance
- validation / fail-closed fields

**Backend does not emit:**

- pixels
- Pixi object ids
- sprite names
- animation names
- easing names
- particle parameters
- canvas layer names

---

The schema is **time/receipt authoritative**, not CSS/pixel authoritative.

---


### Canonical round duration

BATTLE-004 canonical scenario duration is **1200 seconds** (mockup clock: 20:00 allotted).

Shorter durations such as 120 seconds are allowed only as explicit CLI/dev-smoke overrides and must be persisted in `round_config.time_limit_source: "cli_override"` (or equivalent) in fixture metadata.

## 1. Clock authority

Use **one global round clock** for both Red and Blue. Do not use separate Red/Blue clocks as timeline authorities.

Per-team budgets/cooldowns are optional **constraints inside the shared round**, not independent timelines.

```json
{
  "clock": {
    "schema": "battle.clock.v1",
    "round_id": "battle-004-run-...",
    "mode": "live",
    "source": "server_wall_clock",
    "started_at": "2026-07-06T12:00:00Z",
    "server_now": "2026-07-06T12:00:55.200Z",
    "allotted_seconds": 1200,
    "elapsed_seconds": 614.0,
    "remaining_seconds": 586.0,
    "current_seconds": 614.0
  }
}
```

| Field | Meaning |
|-------|---------|
| `elapsed_seconds` | Authoritative run progress |
| `current_seconds` | Playhead position (equals elapsed in live; may differ when scrubbing replay) |

All event timestamps use `at_seconds` relative to global round start.

Optional per-team budgets:

```json
{
  "team_budgets": {
    "red": { "allotted_seconds": 1200, "used_seconds": 614.0, "remaining_seconds": 586.0 },
    "blue": { "allotted_seconds": 1200, "used_seconds": 580.0, "remaining_seconds": 620.0 }
  }
}
```

---

## 2. Playback modes

| Mode | Playhead source | Fixture |
|------|-----------------|---------|
| `live` | Server-authoritative `elapsed_seconds` / `current_seconds` | SSE/JSONL + snapshot |
| `receipt_replay` | Receipt timestamps / replay `current_seconds` | Generated fixture |
| `paused_replay` | Local scrub selection | Same fixture, frozen stream |
| `design_fixture` | `mockup-design-fixture.ts` static/scripted time | `#battle` design parity only |

`clock.mode` + `clock.source` declare which applies. UI must not invent elapsed time in receipt/live modes.

---

## 3. Timeline scroll behavior

Backend may emit **default follow policy**; UI owns `scrollLeft`, viewport width, and user overrides.

| `follow_mode` | Behavior |
|---------------|----------|
| `manual` | User controls scroll; playhead may leave viewport |
| `scroll_after_threshold` | **Default** — follow playhead near right edge |
| `center_playhead` | Cinematic replay; timeline scrolls under fixed playhead |

Prefer percent thresholds in backend schema:

```json
{
  "viewport_defaults": {
    "default_follow_mode": "scroll_after_threshold",
    "follow_threshold_pct": 0.72,
    "can_override_locally": true
  }
}
```

Pixel margins (`edge_margin_px`) are UI implementation constants unless explicitly required.

---

## 4. Animation authority

Backend emits **semantic events** — not animation names, easing, or CSS.

```json
{
  "event_id": "evt-payload-857-materialized",
  "event_type": "red.payload_materialized",
  "event_kind": "payload",
  "lane_id": "payload-857",
  "at_seconds": 33.4,
  "phase": "payload",
  "status_after": "materialized",
  "terminal": false,
  "receipt_id": "tau-red-payload-857-materialized",
  "proof_mode": "receipt_backed"
}
```

UI maps semantic kinds → markers/lines (see `DESIGN.md` §13, §27):

| `event_kind` | UI |
|--------------|-----|
| `payload` | Red marker + line extension |
| `blocked` | Blue shield |
| `killed` | Red skull |
| `fastest_crash` | Green rocket |
| `promoted` | Green survivor/shield |
| `spawn` | Child lane + lineage connector |

`render_intent` strings are transitional adapter hints only — not canonical.

---

## 5. Sparse vs live interpolation

### Receipt replay

Interpolate **only inside receipt-backed segments**:

```json
{
  "segment_id": "seg-payload-857-research",
  "lane_id": "payload-857",
  "kind": "research",
  "start_seconds": 8.0,
  "end_seconds": 21.4,
  "start_event_id": "evt-research-start",
  "end_event_id": "evt-research-complete",
  "proof_mode": "receipt_backed"
}
```

Do not guess continuous progress between arbitrary events.

### Live mode

Optimistic runner movement only inside declared **active/provisional** segments:

```json
{
  "active_segment": {
    "lane_id": "payload-857",
    "kind": "mutate",
    "started_at_seconds": 42.2,
    "last_heartbeat_at_seconds": 48.9,
    "lease_expires_at_seconds": 54.0,
    "provisional": true,
    "pending_receipt": true
  }
}
```

UI distinguishes provisional vs receipt-backed visually. Never interpolate into terminal outcomes before Judge proof.

---

## 6. Parent-child spawn timing

Child lane exists **only after** receipt-backed spawn/handoff event.

```json
{
  "event_type": "tau.spawned_child",
  "event_kind": "spawn",
  "lineage_event": {
    "type": "spawn_child",
    "parent_lane_id": "payload-857",
    "child_lane_id": "payload-857-A",
    "at_seconds": 61.8,
    "lineage_receipt_id": "lineage-spawn-..."
  },
  "proof_mode": "receipt_backed"
}
```

Derived lane:

```json
{
  "id": "payload-857-A",
  "parentId": "payload-857",
  "generation": 2,
  "xStartSeconds": 61.8
}
```

UI may animate row insertion after spawn time; must not pre-draw branches in receipt mode.

---

## 7. Outcome timing (Judge truth)

Agents emit **candidates**; Judge/Arena emits **terminal truth**.

| Agent (non-terminal) | Judge (terminal) |
|----------------------|------------------|
| `red.crash_claimed` | `judge.CRASH_CONFIRMED` |
| `blue.block_attempted` | `judge.BLUE_SUCCESS` / `judge.BLUE_BLOCK_CONFIRMED` |
| `red.payload_materialized` | — |
| — | `judge.PROMOTED_SURVIVOR`, `judge.RED_KILLED` |

Terminal UI states and scoreboard require Judge receipt + `terminal: true`.

---

## 8. Schema shape

Emit both:

```text
events[]  — canonical append-only receipt stream (source of truth)
lanes[]   — renderer-ready derived view (convenience cache)
```

Validators must prove `lanes[]` is consistent with `events[]`. UI **fails closed** on unbacked terminal claims.

Derived lane provenance:

```json
{
  "id": "payload-857-A",
  "source_event_ids": ["evt-lineage-payload-857-spawn-A"],
  "source_receipt_ids": ["lineage-spawn-..."],
  "validation": {
    "derived_from_canonical_events": true,
    "terminal_claims_receipt_backed": true
  }
}
```

---

## 9. Live transport

```text
append-only event stream (SSE or JSONL)  +  periodic snapshot for recovery
generated fixture                        =  replay/regression from same canonical events
```

Live envelope:

```json
{
  "schema": "battle.live_event.v1",
  "run_id": "battle-004-run-...",
  "seq": 184,
  "event_id": "evt-judge-blue-success-payload-857",
  "at_seconds": 72.4,
  "observed_at": "2026-07-06T12:01:12.400Z",
  "event_type": "judge.BLUE_SUCCESS",
  "payload": { "lane_id": "payload-857", "status_after": "blocked", "receipt_id": "..." }
}
```

Client flow:

```text
1. Load latest snapshot
2. Open stream from last_seq + 1
3. Apply events idempotently
4. On gap → reload snapshot
5. Replay mode uses generated fixture from same events
```

---

## 10. Time-limit source

Precedence: **CLI override → scenario config → project default**.

Resolved value must be persisted in run artifacts (`round_config`, `battle_clock`, generated UX fixture). UI never hardcodes round duration.

---

## 11. `battle_timeline_control` (refined)

Backend uses **seconds and normalized percent** — not pixel `x`.

```json
{
  "battle_timeline_control": {
    "schema": "battle.timeline_control.v1",
    "clock_mode": "receipt_replay",
    "time_domain": {
      "start_seconds": 0,
      "end_seconds": 120,
      "allotted_seconds": 1200
    },
    "playhead": {
      "current_seconds": 614.0,
      "current_pct": 46.0,
      "can_animate": true
    },
    "viewport_defaults": {
      "follow_mode": "scroll_after_threshold",
      "follow_threshold_pct": 0.72,
      "can_override_locally": true
    },
    "controls": {
      "can_play": true,
      "can_pause": true,
      "can_scrub": true,
      "can_zoom": true,
      "can_pan": true
    },
    "render_guards": {
      "derive_x_positions_from_elapsed_seconds": true,
      "do_not_draw_lane_progress_before_lane_start": true,
      "do_not_reveal_terminal_outcome_before_receipt_time": true,
      "child_lane_requires_lineage_receipt": true,
      "terminal_outcome_requires_judge_receipt": true,
      "auto_scroll_only_while_playback_active": true
    }
  }
}
```

**Deprecated:** `playhead.current_x` in backend payloads — UI derives x from D3 scale + viewport (see `DESIGN.md` §10).

Types: `lib/battle-types.ts` → `BattleTimelineControlV1`, `BattleClockV1`.

---

## 12. Final decisions (checklist)

1. One global battle clock
2. Per-team budgets optional; not timeline authorities
3. Live playhead → server `current_seconds`
4. Replay playhead → receipt timestamps
5. Default scroll: `scroll_after_threshold`
6. Backend: semantic events; UI: animation
7. Replay interpolation: receipt-backed segments only
8. Live interpolation: active/provisional segments only
9. Child lanes after lineage receipt only
10. Judge owns terminal outcomes
11. `events[]` canonical; `lanes[]` derived with provenance
12. Live: SSE/JSONL + snapshots
13. Time limits: scenario/CLI → receipts; never UI-hardcoded
14. Timeline control: seconds/percent, not backend pixels

---

## Related

| Document | Role |
|----------|------|
| `DESIGN.md` §2, §7, §10, §18, §30 | View modes, coordinates, migration |
| `BATTLE_004_DESIGN_HANDOFF.md` §9 | Python adapter contract |
| `lib/battle-types.ts` | TypeScript contract types |
| `lib/timeline-playback.ts` | UI scroll/zoom/playhead mechanics |
