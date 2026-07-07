# BATTLE Race Engine (Pixi spike)

Engine overview for the BATTLE-004 center race viewport. **Phase 1 spike authority:** `BATTLE_RACE_ENGINE_PIXI_SPIKE.md`. Complements `BACKEND_UX_CONTRACT.md` (clock/events) and `DESIGN.md` (shell parity).

## Stack

```text
React DOM shell + PixiJS race viewport + pixi-viewport camera
@pixi/react v8 (stage lifecycle) + imperative Pixi where needed
D3 time scale math only — no backend pixels
```

Gravity UI Timeline: **reference only** — do not spike a side-by-side branch before Pixi parity gates.

## Rollout

| Phase | Behavior |
|-------|----------|
| **1 (now)** | `BattleRacePixiSpike` behind `#battle?engine=pixi`; DOM `RaceViewport` remains default |
| **2** | Feed design fixture + one receipt-backed sparse fixture; deterministic paused-frame compare |
| **3** | Replace timeline body when parity + qid/a11y mirrors pass |
| **4** | Pixi becomes default center renderer |

## DOM vs Pixi split (v1 hybrid)

**React DOM owns:**

```text
graphTitleBar, zoom buttons, playhead label
TimelineOverview shell/minimap controls
BlueControlStrip container and labels
sticky axis/header labels
sticky lane label column (--label-w: 290px)
tooltips/detail overlays
all qid-bearing controls
accessibility mirrors
Agent Detail
audio policy
```

**Pixi owns:**

```text
runner characters
lane progress tracks (right of label gutter)
receipt-backed / provisional motion
spawn branches and fork effects
block/shield, kill/destroy, fastest-crash, promoted effects
glowing trails
dense event markers inside track body
playhead line inside moving track surface
camera-follow inside track plane
```

## Shared viewport state

DOM overlays and Pixi subscribe to one object — **no independent scroll/camera drift**:

```ts
type BattleTimelineViewportState = {
  zoom: number;
  worldLeftSeconds: number;
  worldRightSeconds: number;
  currentSeconds: number;
  followMode: "scroll_after_threshold" | "center_playhead" | "manual";
  labelWidthPx: 290;
  rowHeightPx: number;
};
```

Coordinate rule:

```text
screen x = labelWidthPx + timeScale(seconds)
```

Gutter is screen-fixed; only the track world pans/zooms.

## Engine input contract

Pixi consumes **normalized adapter output**, not raw SSE/JSONL:

```text
battle.normalized_ux_fixture.v1
  ├── clock
  ├── timeline_control
  ├── events[]
  ├── segments[]
  ├── lanes[]
  ├── validation
  └── claims
```

Authority:

```text
events[] + receipts are canonical
lanes[] + segments[] are derived renderer views
terminal effects key off canonical Judge/receipt-backed events
```

```ts
type BattleRaceEngineInput = {
  fixture: BattleNormalizedUxFixture;
  mode: BattleRaceEngineMode;
  selectedLaneId: string | null;
  viewport: BattleTimelineViewportState;
  onSelectLane(id: string): void;
  onSelectEvent(id: string): void;
  onEffectCue?(cue: BattleEffectCue): void;
  testMode?: BattleEngineRenderTestMode;
};
```

## Engine modes

```ts
type BattleRaceEngineMode = "design_fixture" | "receipt_replay" | "live";
```

- `design_fixture`: mockup density allowed for visual regression
- `receipt_replay` / `live`: fail closed — only proved data

## Provisional vs receipt-backed motion

| State | Visual |
|-------|--------|
| Receipt-backed | Solid trail, normal runner opacity, confirmed markers |
| Provisional | Dashed trail, semi-transparent runner, cyan/yellow pending halo, PENDING in DOM detail |
| Lease expired | Freeze at last heartbeat, dim trail, stale — no terminal effect without receipt |
| Receipt confirms | Solidify trail, remove halo, settle to receipt keyframe |

## Event → effect mapping

```text
research          -> runner jogging / scanning
payload           -> runner sprint / payload glow
useful            -> yellow ping
handoff / spawn   -> parent fork + child materialize burst
blocked           -> blue shield impact
killed            -> red destroy burst
fastest_crash     -> green rocket streak (Judge-confirmed only)
promoted          -> green survivor/shield elevation
```

Rule: **receipt-backed event enables effect; missing receipt disables effect.** No filler particles or fake terminals.

## Assets (v1)

Procedural Pixi shapes + placeholder semantic sprites. No Rive, no mockup PNG crops.

Theme interface (`engine/battle-sprite-theme.ts`) allows later atlas/Rive swap without API change.

## QID / interaction strategy

Required: **DOM hit-target mirrors** for every interactive Pixi lane/marker/event.

Pixi may handle hover glow; canonical interaction surface for tests, keyboard, qids, and a11y is DOM.

## Screenshot regression

Two gates:

1. **Shell parity** — header, rails, blue strip chrome, agent pane, footer (existing compare scripts)
2. **Engine parity** — center timeline at deterministic paused frame

```ts
type BattleEngineRenderTestMode = {
  freezeTime: true;
  currentSeconds: number;
  disableParticles: boolean;
  deterministicSeed: string;
};
```

## Audio

Visuals-only in spike. Engine emits `BattleEffectCue`; React shell connects to `useBattleSound` later.

## Wrapper API

```tsx
<BattleRaceEngine
  fixture={normalizedUxFixture}
  selectedLaneId={selectedLaneId}
  playback={playbackState}
  onSelectLane={setSelectedLaneId}
/>
```

Spike implementation: `engine/BattleRacePixiSpike.tsx` (Phase 1).

## Forbidden

```text
backend pixels / animation names
Pixi-only qid testing as primary gate
fake terminal effects
child branch before lineage receipt
terminal outcome before Judge receipt
independent DOM scroll vs Pixi camera
```

## Agent skills (two-layer)

```text
Layer 1 — Official PixiJS (generic v8 API)
  agent-skills/skills/pixijs*  →  experiments/pixijs-skills
  Upstream: https://github.com/pixijs/pixijs-skills

Layer 2 — Battle overlay (project constraints only)
  agent-skills/skills/best-practices-battle-pixi
```

Before implementing Pixi code: load `pixijs` router + relevant `pixijs-*` skill, then `best-practices-battle-pixi`.

Do **not** duplicate PixiJS API guidance in Battle docs — only Battle-specific boundaries live here and in the overlay skill.


## Spike acceptance (Phase 1)

```text
[ ] React 19 build passes
[ ] Pixi canvas fits inside .graphWrapHost track area (right of 290px gutter)
[ ] Time axis derives from allotted_seconds / current_seconds
[ ] Viewport pan/zoom/follow playhead (synced with DOM scroll state)
[ ] Runners move only inside receipt-backed / provisional segments
[ ] DOM qid mirrors for selectable lanes/events
[ ] Fixed-time screenshot mode (testMode)
[ ] Default #battle unchanged (no ?engine=pixi)
```

## Related files

| File | Role |
|------|------|
| `lib/battle-types.ts` | `BattleRaceEngineInput`, viewport state, effect cues |
| `lib/is-battle-pixi-engine.ts` | `#battle?engine=pixi` gate |
| `lib/build-race-engine-input.ts` | Fixture → engine input |
| `engine/BattleRacePixiSpike.tsx` | Phase 1 spike |
| `engine/PixiHitTargetMirrors.tsx` | DOM interaction mirrors |
| `engine/battle-sprite-theme.ts` | Procedural display specs |
| `battle-pixi-engine.css` | Canvas host + hit-target styles |
