# BATTLE Race Engine — Pixi Phase 1 Spike Contract

| Field | Value |
|-------|-------|
| **Version** | 0.1 Phase 1 spike |
| **Status** | Authoritative for `#battle?engine=pixi`; not yet default renderer |
| **Default route** | Current DOM/SVG `RaceViewport` remains default |
| **Truth authority** | `BACKEND_UX_CONTRACT.md` + receipt-backed fixture |
| **Visual authority** | `DESIGN.md` + HTML mockup + element crops |
| **Companion** | `BATTLE_RACE_ENGINE.md` (engine overview), `best-practices-battle-pixi` (agent overlay skill) |

This document does **not** change backend truth semantics. The backend remains renderer-neutral.

---

## Purpose

Phase 1 contract for `BattleRacePixiSpike` — the optional Pixi animated race world inside BATTLE-004's center timeline. This is an **engine migration companion**, not a rewrite of `DESIGN.md`.

```text
React DOM shell
+ Pixi animated race world
+ D3 time math
+ normalized receipt-backed fixture
+ DOM qid/a11y mirrors
+ fail-closed receipt truth
```

Gravity UI Timeline: **reference only** — do not spike a side-by-side branch before Pixi parity gates.

---

## Route gate

```text
Default:  http://127.0.0.1:3012/#battle
Spike:    http://127.0.0.1:3012/#battle?engine=pixi
```

`isBattlePixiEngine()` returns true only when `engine=pixi` query param is present on a design-view route.

---

## DOM vs Pixi boundary

### React DOM owns

- `BattleHeader`, scoreboard, live events
- `SpectatorRail`
- `BlueControlStrip` chrome and labels
- `graphTitleBar`, zoom controls, playhead label
- `TimelineOverview` shell
- sticky axis text
- sticky lane label column
- `MockupAgentDetailPane` / `AgentDetailPane`
- footer controls
- tooltips / receipt overlays
- `data-qid` / `data-qs-action`
- keyboard accessibility
- audio policy

### Pixi owns

- runner characters
- lane progress tracks (right of label gutter)
- receipt-backed / provisional motion
- spawn / fork / materialization effects
- lineage branch visuals
- block / shield impacts
- killed / destroy bursts
- fastest-crash rocket effects
- promoted-survivor effects
- glowing trails
- dense event marker rendering inside track body
- playhead line inside moving track plane
- camera follow inside track plane

---

## Canvas / gutter geometry

Lane labels stay DOM/sticky. Pixi draws only in the **track plane**.

Pixi may mount inside `.graphWrapHost`, but the active Pixi world must be **clipped to the track plane** to the right of the fixed label gutter.

The DOM label gutter remains screen-fixed at `--label-w: 290px`.

Pixi must never draw runners, tracks, markers, trails, or effects under the label gutter.

Coordinate rule:

```text
screenX = labelWidthPx + timeScale(seconds)
```

### Pixi host CSS

```css
.battleRaceStageHost {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.battleRaceTrackPlane {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: var(--label-w, 290px);
  overflow: hidden;
}

.battleRacePixiCanvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.battlePixiHitMirrorLayer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 30;
}

.battlePixiHitMirror {
  position: absolute;
  pointer-events: auto;
  opacity: 0;
  border: 0;
  background: transparent;
}
```

---

## Shared viewport state

DOM overlays and Pixi subscribe to one object. **No independent scroll/camera drift.**

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

Use refs or an external viewport store for high-frequency camera/playhead updates — not React state on every tick.

---

## Engine input contract

Pixi consumes **normalized adapter output** only (`battle.normalized_ux_fixture.v1`). Not raw SSE/JSONL.

```ts
type BattleRaceEngineInput = {
  fixture: BattleNormalizedUxFixtureV1;
  mode: BattleRaceEngineMode;
  selectedLaneId: string | null;
  viewport: BattleTimelineViewportState;
  onSelectLane(id: string): void;
  onSelectEvent(id: string): void;
  onEffectCue?(cue: BattleEffectCue): void;
  testMode?: BattleEngineRenderTestMode;
};

type BattleRaceEngineMode = "design_fixture" | "receipt_replay" | "live";
```

`BattleNormalizedUxFixtureV1` is the versioned name for `schema: "battle.normalized_ux_fixture.v1"` (alias: `BattleNormalizedUxFixture` in `lib/battle-types.ts`).

Authority:

```text
events[] + receipts are canonical
lanes[] + segments[] are derived renderer views
terminal effects key off canonical Judge/receipt-backed events
```

### Validation gate

The engine must check `fixture.validation.fail_closed` and terminal proof fields before rendering receipt-mode terminal effects.

In receipt mode, if validation is missing or false, render a sparse safe fallback and surface a DOM warning. **Do not** render terminal effects from unvalidated derived lanes.

---

## Time domain (no backend pixels)

```text
[ ] Time domain derives from fixture timeline_control.time_domain
[ ] Playhead derives from clock.current_seconds
[ ] Event x positions derive from event/segment at_seconds, start_seconds, end_seconds
[ ] No backend pixel x values are consumed
```

```ts
const x = labelWidthPx + timeScale(event.at_seconds);
```

---

## Receipt-safe effects

| Condition | Pixi effect |
|-----------|-------------|
| receipt-backed spawn | child materialization / branch effect |
| receipt-backed blocked | blue shield impact |
| receipt-backed killed | red destroy burst |
| receipt-backed fastest_crash | green rocket streak |
| receipt-backed promoted | green survivor / shield effect |
| provisional active segment | dashed/dim runner, pending halo |

**Forbidden:** fake branches, kills, crashes, promotions, dense filler particles, terminals before Judge receipt, progress before lane start, child lane before lineage receipt.

Rule: **receipt-backed event enables effect; missing receipt disables effect.**

### Effect cues (audio hook — visuals-only in Phase 1)

```ts
type BattleEffectCue = {
  eventId: string;
  laneId: string;
  cue:
    | "spawn"
    | "blocked"
    | "killed"
    | "fastest_crash"
    | "promoted"
    | "useful";
  atSeconds: number;
  receiptId: string;
  proofMode: "receipt_backed" | "live" | "design_fixture";
};
```

`onEffectCue` must be emitted **once per event crossing**, not once per animation frame. React shell may connect to `useBattleSound` later.

---

## Asset pipeline (spritesheets)

### Phase 1 spike — **no sprite sheets required**

Phase 1 uses **procedural `Graphics`** via `BattleSpriteTheme` / `proceduralBattleSpriteTheme`:

- runners → circles/glyphs
- markers → small shapes
- effects → strokes / rings (upgrade to `ParticleContainer` per `pixijs-scene-particle-container`)

This matches `pixijs-scene-graphics` and is sufficient for parity / receipt-truth validation.

Do **not** cut sprites from mockup PNG crops or build atlases before Phase 1 gates pass.

### When sprite sheets become appropriate (Phase 2+)

Production BATTLE exploit agents should become real animated sprites after the
Phase 1 Pixi spike proves the viewport, qid mirrors, clock, and receipt gates.

Target art direction:

```text
original 16-bit side-view grimdark sci-fi pixel art
vintage Sega Genesis-like feel
transparent PNG sheets
nearest-neighbor scaling
48x48 normal agents, 64x64 heavy agents
```

The first complete production contract is:

| State | Frames | FPS | Loop | Receipt gate |
|-------|-------:|----:|------|--------------|
| `idle` | 4 | 4-6 | yes | none |
| `walk` | 6 | 8 | yes | active/provisional segment |
| `run` | 8 | 12 | yes | active/provisional segment |
| `research` | 6 | 6-8 | yes | research/scan event or segment |
| `payload` | 6 | 10 | yes | payload/materialization event or segment |
| `mutate` | 6 | 8 | yes | mutation/retry event or segment |
| `handoff` | 6 | 8 | no | handoff event |
| `spawn` | 8 | 10 | no | lineage spawn receipt |
| `hit` | 3 | 12 | no | non-terminal impact/intercept event |
| `blocked` | 6 | 10 | no | Blue/Judge block receipt |
| `killed` | 8 | 10 | no | Judge kill receipt |
| `promoted` | 8 | 8 | no | promotion receipt |
| `fastest_crash` | 8 | 14 | no | crash proof + timing receipt |

Minimum v1 sheet set per exploit:

```text
idle
run
research
payload
spawn
blocked
killed
```

Full set:

```text
idle
walk
run
research
payload
mutate
handoff
spawn
hit
blocked
killed
promoted
fastest_crash
```

Use 10-15 original BATTLE character variants initially, not one-off art for
every lane forever. Shared skeleton families are acceptable:

```text
light runner
heavy brute
support/banner
blue defender
child/imp
survivor
```

Use reusable effect sheets for:

```text
spawn burst
shield impact
red destroy burst
green rocket streak
promotion glow
yellow useful signal
purple handoff fork
blue block ring
debris particles
```

Sprite authoring manifests are validated by:

```text
skills/battle/schemas/battle.sprite_sheet_manifest.v1.schema.json
```

The UI-owned Pixi theme manifest is validated by:

```text
skills/battle/schemas/battle.sprite_theme.v1.schema.json
```

Add a texture atlas when **all** of these are true:

- art direction is locked (runner poses, shield, skull, rocket, spawn burst)
- lane/event count makes per-frame `Graphics.clear()` costly (profile first — `pixijs-performance`)
- animations need multi-frame `AnimatedSprite` sequences

Then follow **`pixijs-assets`** + **`pixijs-scene-sprite`**:

```ts
import { Application, Assets, Sprite, AnimatedSprite } from "pixi.js";

await Assets.init({ basePath: "/battle-race/" });
const sheet = await Assets.load("battle-race-atlas.json");

const runner = new Sprite(sheet.textures["runner-red.png"]);
const shieldFx = new AnimatedSprite(sheet.animations["shield-impact"]);
```

Keep semantic mapping in `BattleSpriteTheme`:

```text
backend actor_visual.variant_id + actor_visual.state
  -> sprite_theme.variants[variant_id].spritesheet_alias
  -> sprite_theme.variants[variant_id].state_animation_map[state]
  -> sheet.animations[animationName]
```

The backend still emits semantic states and receipt-backed timings only. It
must not emit Pixi aliases, spritesheet paths, animation names, or frame ids.

### Not planned for Phase 1

- Rive state machines
- mockup PNG crop atlases
- backend-driven sprite names or frame ids


## Reduced motion

Pixi animations must respect `prefers-reduced-motion`.

When reduced motion is enabled:

- disable particle bursts
- disable camera snap/deceleration flourish
- keep playhead position accurate
- show terminal markers without cinematic bursts
- keep qid mirrors and Agent Detail behavior unchanged

Deterministic screenshot mode:

```ts
type BattleEngineRenderTestMode = {
  freezeTime: true;
  currentSeconds: number;
  disableParticles: boolean;
  deterministicSeed: string;
};
```

---

## qids and accessibility

Pixi-only interaction is **not** acceptable.

Every selectable Pixi lane, marker, and outcome needs a DOM hit-target mirror:

```tsx
<button
  type="button"
  data-qid="battle:timeline:event:payload-857:blocked"
  data-qs-action="BATTLE_EVENT_SELECT"
  title="Select blocked event for payload-857"
  aria-label="Blocked event for payload-857"
  className="battlePixiHitMirror"
  style={{
    transform: `translate(${screenX}px, ${screenY}px)`,
    width,
    height,
  }}
  onClick={() => onSelectEvent(event.id)}
/>
```

Canvas-coordinate CDP tests are not the primary interaction gate.

---

## Pixi lifecycle / performance

- Destroy Pixi `Application` on React unmount (`releaseGlobalResources: true`).
- Remove ticker callbacks on unmount.
- Disconnect `ResizeObserver` on unmount.
- Cap renderer resolution/pixel ratio if needed for screenshot stability.
- Do not mirror every Pixi frame into React state.
- Use refs or an external viewport store for high-frequency camera/playhead updates.
- React state updates on selection, mode change, fixture change, or control change — **not every tick**.
- Reuse display objects where practical; do not recreate all sprites every frame.

Approved deps (isolated behind `BattleRaceEngine`): `@pixi/react` v8, `pixi-viewport`, `pixi.js` v8.

---

## Required skill context

Before implementing this spike, load the official PixiJS skill collection:

```bash
npx skills add https://github.com/pixijs/pixijs-skills
```

Use official PixiJS skills for Application, Ticker, Events, Graphics, Accessibility, DOMContainer, Assets, and Performance.

Then apply the local Battle Pixi overlay: `$best-practices-battle-pixi`.

Official Pixi skills = how to use PixiJS correctly.  
This document + overlay skill = how to use PixiJS safely inside BATTLE-004.

---

## Component map (spike)

```text
.graphWrapHost
├── DOM path (default)
│   └── .graphWrap → .timelineShell → LaneRow, BattleLineageFlow, playheadOverlay
└── Pixi path (#battle?engine=pixi)
    └── BattleRaceEngine / BattleRacePixiSpike
        ├── BattleRacePixiStage
        ├── BattlePixiTrackLayer
        ├── BattlePixiRunnerLayer
        ├── BattlePixiLineageLayer
        ├── BattlePixiEffectsLayer
        ├── BattlePixiPlayheadLayer
        └── BattlePixiHitTargetMirrorLayer   DOM overlay
```

---

## Phase 1 acceptance

```text
[ ] #battle default route still uses DOM/SVG RaceViewport
[ ] #battle?engine=pixi mounts BattleRacePixiSpike
[ ] Existing React shell visually unchanged
[ ] Pixi mounts inside .graphWrapHost track plane (right of --label-w)
[ ] DOM graphTitleBar, Blue strip, overview, axis, sticky labels remain
[ ] Time domain derives from fixture timeline_control.time_domain
[ ] Playhead derives from clock.current_seconds
[ ] Event x from at_seconds / segment seconds — no backend pixel x
[ ] mockupDesignLanes in design_fixture mode
[ ] one receipt-backed sparse fixture in receipt_replay mode
[ ] sparse fixture stays sparse
[ ] parent-child branch only after lineage event
[ ] block / kill / fastest_crash / promoted effects only after receipts
[ ] provisional segments: pending/dashed/dim, not terminal
[ ] DOM hit-target mirrors for selectable lanes/events/outcomes
[ ] qid verification includes mirror targets
[ ] Agent Detail updates from mirror selection
[ ] deterministic screenshot mode (BattleEngineRenderTestMode)
[ ] validation.fail_closed respected in receipt mode
[ ] npm run build passes
```

### Verification commands

```bash
cd pi-mono/packages/ux-lab
UX_LAB_UI_PORT=3012 UX_LAB_API_PORT=3011 npm run dev

# Pixi spike route
# ~/.codex/hooks/verify-ui-cdp.sh \
#   --url "http://127.0.0.1:3012/#battle?engine=pixi" \
#   --name battle-agent-cockpit-pixi

# Default design route must still pass
./scripts/verify-battle-ui.sh
python3 scripts/compare-battle-mockup.py
npm run build
```

---

## Related files

| File | Role |
|------|------|
| `engine/BattleRacePixiSpike.tsx` | Phase 1 spike implementation |
| `engine/PixiHitTargetMirrors.tsx` | DOM qid mirrors |
| `lib/battle-types.ts` | `BattleRaceEngineInput`, `BattleEffectCue`, viewport types |
| `lib/is-battle-pixi-engine.ts` | `?engine=pixi` gate |
| `BATTLE_RACE_ENGINE.md` | Engine overview / rollout |
| `BACKEND_UX_CONTRACT.md` | Renderer-neutral clock/events |
| `DESIGN.md` | Shell parity / mockup authority |

## Changelog

| Date | Version | Change |
|------|---------|--------|
| 2026-07-06 | 0.1 | Initial Phase 1 Pixi spike contract |
