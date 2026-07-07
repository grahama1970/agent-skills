# BATTLE-004 Interface Implementation Spec

**Timestamp**: 2026-07-06T12:42:20Z  
**Status**: Authoritative index — full detail lives in ux-lab `DESIGN.md`  
**Route**: `#battle` · Viewport: 1672×941

## Purpose

This document tells a **frontend project agent how to build** the accepted BATTLE-004 spectator interface: layout, components, CSS, animations, state, and verification.

The agent **must not invent receipt-backed race outcomes**. It **must** implement the visual shell, timeline, and interaction model described here and in `DESIGN.md`.

**Read order (orientation):**

1. This file — modes, authority, checklist
2. `pi-mono/packages/ux-lab/src/components/battle/dual-agent/DESIGN.md` — complete mechanical spec
3. `skills/battle/mockups/battle-004-shell-preserving-scroll-timeline.html` — class authority
4. `BATTLE_004_DESIGN_HANDOFF.md` — receipt truth boundary

---

## Authority precedence

**When truth and visual density conflict, truth wins.**

### For truth / data claims

1. Arena / Tau / Judge receipts (live proof artifacts)
2. Generated receipt-backed normalized fixture (`receiptBackedFixture`)
3. `BATTLE_004_DESIGN_HANDOFF.md`
4. This implementation spec
5. `DESIGN.md` / HTML mockup (structure only — not permission to invent data)

### For visual / layout implementation

1. `DESIGN.md` (ux-lab)
2. HTML mockup class authority
3. Element crops + `assets/battle-mockup/reference.png`
4. This implementation spec
5. `BATTLE_004_DESIGN_HANDOFF.md`

---

## Fixture modes (non-negotiable)

Two modes share the **same DOM class vocabulary** but differ in **data authority**. Do not conflate them.

### Design parity mode

| Field | Value |
|-------|-------|
| **Gate** | `isBattleDesignView()` → `#battle` or `#battle/isolation` |
| **Lanes** | `mockupDesignLanes` (`MOCK_SPECS` in `battle-mockup-lanes.ts`) |
| **Purpose** | Reproduce accepted visual mockup; regression-test shell geometry; pixel compare vs reference PNG |
| **Dense state** | **Allowed** — mockup may include 11 lanes, fastest crash, promotion, kills, child branches for **visual parity only** |
| **Label** | Treat as **design fixture** — not truthful live Battle status |

### Receipt-backed mode

| Field | Value |
|-------|-------|
| **Gate** | Non-design `#battle*` routes / receipt shell |
| **Lanes** | `receiptBackedFixture.lanes` via `battle_event_adapter.py` |
| **Purpose** | Truthful Battle spectator over generated receipts |
| **Dense state** | **Forbidden unless proven** — child lanes, fastest crash, promotion, kill, blocked handoff, replay CTA only when fixture contains receipt id + `proofMode` |
| **Label** | Only mode allowed for truthful Battle status claims |

```text
Hard rule (receipt-backed mode only):
No receipt-mode event kind appears unless the receipt-backed fixture contains
that event with receiptId and proofMode.

Design parity mode may show mockup-dense states for screenshot regression.
Never copy mockupDesignLanes into receipt mode or claim receipt proof from design mode.
```

---

## 1. Visual target

Dark acrylic neon battle cockpit. Dense horizontal race timeline (DAW / video-editor style). Not a card dashboard.

| Token | Role |
|-------|------|
| Red | Exploit progress, killed, red team |
| Blue | Patches, blocks, blue team |
| Green | Fastest crash, promoted survivor, lineage |
| Yellow | Useful signal |
| Purple | Child lanes, handoff |
| Cyan | Playhead |

Reference images: `pi-mono/packages/ux-lab/assets/battle-mockup/reference.png` and `assets/battle-mockup/elements/*.png` (`DESIGN.md` §25).

---

## 2. React component tree (implemented)

Package: `pi-mono/packages/ux-lab/src/components/battle/dual-agent/`

```text
BattleArenaView
└── BattleSpectatorArena          .battle-mockup-app / .battle-mockup-shell
    ├── BattleHeader              .topbar
    ├── .battle-mockup-main       grid 260px | 1fr | 360px
    │   ├── SpectatorRail         .leftRail
    │   ├── RaceViewport          .center (+ BlueControlStrip inside)
    │   │   ├── BlueControlStrip  .blueStripCenter
    │   │   ├── .graphTitleBar    zoom + playhead label
    │   │   ├── TimelineOverview  .timelineOverview
    │   │   └── .graphWrapHost
    │   │       ├── DOM renderer path (current default)
    │   │       │   └── .graphWrap → .graph → .timelineShell
    │   │       │       ├── BattleTimelineAxis   .axis / .stage
    │   │       │       ├── LaneRow × N          .row
    │   │       │       ├── BattleLineageFlow    SVG paths
    │   │       │       └── .playheadOverlay
    │   │       └── Pixi renderer path (`#battle?engine=pixi` spike only)
    │   │           └── BattleRaceEngine
    │   │               ├── BattleRacePixiStage
    │   │               ├── BattlePixiTrackLayer
    │   │               ├── BattlePixiRunnerLayer
    │   │               ├── BattlePixiLineageLayer
    │   │               ├── BattlePixiEffectsLayer
    │   │               ├── BattlePixiPlayheadLayer
    │   │               └── BattlePixiHitTargetMirrorLayer   DOM overlay
    │   └── MockupAgentDetailPane .right
    ├── BattleMockupLegend        .footerLegend
    └── BattleMockupFooter        .footer
```

Supporting: `BattleTimelineProvider`, `LaneEventMarker`, `LaneEventLabel`, `BattlePlayheadCursor`, `lib/timeline-playback.ts`, `lib/mockup-lane-partition.ts`.

---

## 3. Locked technology stack

| Layer | Choice | Notes |
|-------|--------|-------|
| UI shell | React 19 + TypeScript | `dual-agent/` |
| Design chrome | `battle-mockup-elements.css` | `.battle-mockup-shell .{class}` remains authority |
| Time → x mapping | D3 `scaleLinear` | Shared by DOM renderer and Pixi renderer |
| Current design renderer | DOM + SVG + CSS | Default until Pixi parity gates pass |
| Race engine spike | PixiJS v8 + `@pixi/react` + `pixi-viewport` | Behind `#battle?engine=pixi` |
| Icons / DOM markers | Lucide via `battle-icons.tsx` | Used in current DOM renderer and DOM mirrors |
| Interactions | `data-qid` + `useRegisterAction` | DOM controls and Pixi hit-target mirrors |

**Renderer status:**

- **Current default:** DOM/SVG/CSS `RaceViewport`.
- **New spike:** `BattleRacePixiSpike` / `BattleRaceEngine` behind `#battle?engine=pixi`.
- Pixi must **not** replace the default route until parity, qid, accessibility, and receipt-truth gates pass.

**Forbidden unless an explicit architecture decision replaces the current renderer:**

- `dnd-timeline`
- `@xyflow/react`
- shadcn `Button`/`Badge` on design mockup chrome
- framer-motion pulse loops on design-view markers
- backend-owned pixel coordinates
- Pixi-only qid testing

**Rendering strategy (hybrid):**

- **DOM** — cockpit shell, panels, text, sticky lane labels, controls, phase labels, qids, accessibility mirrors
- **SVG** — lineage spawn branches (DOM renderer path; Pixi path uses procedural lineage layer)
- **CSS** — playhead (DOM path), markers, hover/selected, scroll hints, glass panels
- **Canvas/Pixi** — allowed **only inside the center race-world body**, not for the cockpit shell, qid controls, sticky labels, Agent Detail, or accessibility mirror


## 3.1 BattleRaceEngine renderer architecture

BATTLE-004 uses a **hybrid renderer**.

React DOM remains responsible for the cockpit shell, text, sticky layout, qids, accessibility, and control surfaces.

Pixi owns only the animated race world inside the center timeline body.

The Pixi renderer must mount inside the same `.graphWrapHost` bounds and preserve the existing outer shell geometry.

### DOM owns

- `BattleHeader`
- scoreboard
- live events
- `SpectatorRail`
- `BlueControlStrip` chrome and labels
- `graphTitleBar`
- zoom controls
- playhead label
- `TimelineOverview` shell
- sticky axis text
- sticky lane label column
- `MockupAgentDetailPane`
- footer controls
- tooltips / receipt overlays
- `data-qid` / `data-qs-action`
- keyboard accessibility
- audio policy

### Pixi owns

- runner characters
- lane progress tracks to the right of `--label-w`
- receipt-backed / provisional motion
- spawn / fork / materialization effects
- lineage branch visuals
- block / shield impacts
- killed / destroy bursts
- fastest-crash rocket effects
- promoted-survivor effects
- glowing trails
- dense event marker rendering inside the track body
- playhead line inside the moving track plane
- camera follow behavior inside the track plane

### Shared state

DOM overlays and Pixi must use one shared timeline viewport model.

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

Do not allow DOM scroll and Pixi camera state to drift independently.


---

## 4. CSS architecture

- `battle-mockup-elements.css` — mockup rules under `.battle-mockup-shell`
- `battle-race.css` — zoom buttons, legacy aliases
- `lib/layout-constants.ts` — `--label-w: 290px`, rail 260px, detail 360px

Shell grid: topbar (auto) · main (1fr) · legend (34px) · footer (64px); main columns `260px | 1fr | 360px`.

**Critical layout rule:**

```text
Reserve fixed lane-label gutter (--label-w: 290px).
Markers and phase labels must never render under label cells.
```

Center scroll shell: `.center` → `.graphWrapHost` → `.graphWrap` → `.graph` → `.timelineShell`.


### Pixi host CSS

Pixi must not break the accepted shell grid.

```css
.battleRaceStageHost {
  position: relative;
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
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

The fixed lane-label gutter remains authoritative:

```text
--label-w: 290px
```

Pixi world-space begins after the gutter:

```text
screenX = labelWidthPx + timeScale(at_seconds)
```

Pixi must never render tracks, event markers, runners, or effects under the sticky label column.


---

## 5. Layout by region

| Region | Ref crop | Key classes |
|--------|----------|-------------|
| Header | `elements/01-header.png` | `.topbar`, `.score`, `.liveEvents` |
| Blue strip | `elements/05-blue-strip.png` | `.blueStripCenter`, `.bluePatch` |
| Left rail | `elements/04-left-rail.png` | `.leftRail`, `.leaderItem` |
| Timeline | `elements/09-timeline-lanes.png` | `.rows`, `.row`, `.markerIcon` |
| Agent detail | `elements/11-agent-detail.png` | `.right`, `.field` |
| Footer | `elements/13-footer.png` | `.footer`, `.footChip` |

Per-element detail: `DESIGN.md` §26.

---

## 6. Timeline rendering

**Coordinate system** (`DESIGN.md` §10):

- Mockup T domain: 0–30 → track % 0–100
- **Design parity mode:** axis labels from `mockupTimelineTicks()` — reference window ~10:04–10:14 on the visible ruler; round clock in header may show ~10:14 / 20:00 independently
- **Receipt-backed mode:** derive axis labels from fixture `battle_clock` / elapsed-axis model — **do not hardcode** `10:04`, `10:14`, or mockup scores
- Single D3 scale from `[data-battle-timeline-track]` width minus 290px label column

**Lane bands:** `:top:` → `.laneTop`; `:above:` → `.laneMidAbove`; `:icon:` → `.markerIcon`; `:bottom:` → `.laneBottom`.

**Lineage:** SVG branches only when parent `children` exist in the active fixture.


### Pixi timeline rendering rules

The backend emits seconds, not pixels.

The UI derives x positions with the shared D3 scale:

```ts
const x = labelWidthPx + timeScale(event.at_seconds);
```

Pixi world coordinates are relative to the track plane, not the full cockpit shell.

Rules:

- The lane-label gutter is fixed at 290px.
- DOM lane labels remain sticky/fixed.
- Pixi tracks scroll/zoom to the right of the gutter.
- Child lane start equals spawn/materialization time.
- Parent-child branch appears only after lineage receipt.
- Terminal effects appear only after Judge receipt.
- Provisional live movement must be visually distinct from receipt-backed movement.


---

## 7. Animation rules

Registry: `DESIGN.md` §27.

1. Animate `transform` and `opacity`, not layout.
2. Design-view markers are **static** (no framer-motion loops).
3. Playhead may animate when `playing` in receipt mode.
4. **All** new timeline, marker, playhead, collapse, hover, and receipt-mode animations **must** respect `prefers-reduced-motion`.
5. Never animate fake state in receipt-backed mode.



### Pixi effect mapping

Backend emits semantic events. Pixi maps them to effects.

| Event kind | Pixi effect |
|------------|-------------|
| `research` | runner scan / jog state |
| `payload` | red sprint / payload glow |
| `useful` | yellow signal ping |
| `handoff` / `spawn` | fork branch + child materialization burst |
| `blocked` | blue shield impact |
| `killed` | red destroy burst |
| `fastest_crash` | green rocket streak |
| `promoted` | green survivor / shield elevation |

Sprite states are semantic. Pixi maps them through `battle.sprite_theme.v1`;
the backend must not emit Pixi animation names or frame indices.

Production sprite direction:

```text
original 16-bit side-view grimdark sci-fi pixel art
vintage Sega Genesis-like feel
48x48 normal agents, 64x64 heavy agents
transparent PNG spritesheets
nearest-neighbor scaling
```

Minimum production agent sheet states:

```text
idle, run, research, payload, spawn, blocked, killed
```

Full sheet states:

```text
idle, walk, run, research, payload, mutate, handoff, spawn,
hit, blocked, killed, promoted, fastest_crash
```

**Receipt-backed mode rules:**

- No spawn burst without lineage receipt.
- No blocked shield impact without Judge/Blue receipt.
- No killed burst without Judge kill receipt.
- No fastest-crash rocket without crash proof and timing receipt.
- No promoted-survivor effect without promotion receipt.
- No dense filler effects to hide sparse receipts.

**Live provisional rules:**

- Provisional active segment may show dashed/dim runner motion.
- Provisional movement must show pending state.
- If lease expires, freeze or dim the runner.
- Never convert provisional state into terminal state without Judge proof.

All Pixi animations must support deterministic screenshot mode:

```ts
type BattleEngineRenderTestMode = {
  freezeTime: true;
  currentSeconds: number;
  disableParticles: boolean;
  deterministicSeed: string;
};
```

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 1ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 1ms !important;
  }
}
```

---

## 8. State model

**UI state (presentation only):** `selectedId`, `collapsed`, `filter`, `zoom`, `playing`, `speed`.

**Fixture state (immutable):** `Lane[]` from active mode’s source. Do not store receipt-derived truths in React state.

---

## 9. Data-to-visual mapping

Icon semantics are part of the interface language (`LaneEventMarker` + `mockupMarkerClasses`):

| Event kind | Visual | Lucide (design) |
|------------|--------|-----------------|
| research, payload, mutate, retry | `.phaseLabel.top` | — |
| useful | yellow token / `tokYellow` marker | Lightbulb |
| handoff / spawn | purple marker + green lineage branch | GitBranch |
| blocked | blue shield marker (`.terminal`) | ShieldX |
| killed | red skull marker (`.terminal`) | Skull |
| **fastest_crash** | green rocket marker (`.big` `.terminal`) | Rocket |
| **promoted** | green shield/survivor marker (`.big` `.terminal`) | ShieldCheck |

```text
Receipt-backed mode: no row in this table may render without a matching fixture event + proof.
Design parity mode: mockup fixture may populate all rows for regression only.
```

---

## 10. Interaction / accessibility

Every interactive control uses the **4-attribute rule**:

1. `data-qid` — stable selector (`component:element:qualifier`)
2. `data-qs-action` — uppercase action id
3. `title` — human-readable tooltip
4. `useRegisterAction` — registered at parent component top level (not inside `.map()`)

Example (matches shipped footer):

```tsx
<button
  type="button"
  data-qid="battle:footer:speed:2x"
  data-qs-action="BATTLE_SPEED_SET"
  title="Set replay speed to 2x"
  className="footChip min-h-11 ..."
  onClick={() => setSpeed("2x")}
>
  2x
</button>

// In BattleMockupFooter (top of function body):
useRegisterAction("battle:footer:speed", {
  app: "ux-lab",
  action: "BATTLE_SPEED_SET",
  label: "Set Battle Replay Speed",
  description: "Set Battle design-view replay speed.",
  tags: ["battle", "design"],
});
```

Touch targets: `min-h-11` on footer chips, zoom buttons, collapse toggles. `focus-visible` rings on buttons.



### Pixi qid / accessibility rule

Pixi-only interaction is **not** acceptable for BATTLE-004.

Every selectable Pixi lane, marker, and outcome must have an aligned transparent DOM hit-target mirror.

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

The DOM mirror layer is required for:

- qid testing
- keyboard selection
- screen-reader labels
- focus-visible behavior
- Agent Detail selection updates

Canvas-coordinate CDP tests are not the primary interaction gate.


Test manifest: `battle-design-interactions.json` · `test-interactions` skill · `http://127.0.0.1:3012/#battle`

---

## 11. Verification commands

```bash
cd /home/graham/workspace/experiments/pi-mono/packages/ux-lab

# Dev server (if npm run dev hits ENOSPC):
UX_LAB_UI_PORT=3012 UX_LAB_API_PORT=3011 npm run dev
# or: npx vite --host 127.0.0.1 --port 3012

# QID gate (must be 100%):
python3 scripts/verify-data-qid.py src/components/battle/dual-agent/

# Live structural + pixel regression (#battle design mode):
./scripts/verify-battle-ui.sh
python3 scripts/compare-battle-mockup.py

# Full interaction fidelity (test-interactions skill — live CDP):
# ~/.cursor/skills/test-interactions/run.sh run \
#   --manifest src/components/battle/dual-agent/battle-design-interactions.json \
#   --output-dir .artifacts/battle-interactions/
# Expected: 57 PASS / 0 FAIL (2026-07-06 baseline)

# Element screenshot vs mockup crops (required after interaction run):
python3 scripts/compare-battle-element-captures.py \
  --capture .artifacts/battle-interactions/battle-design/0001_shell-mockup-fidelity_screenshot.png

# Optional CDP screenshot (adjust port if needed):
# ~/.codex/hooks/verify-ui-cdp.sh --url http://127.0.0.1:3012/#battle --name battle-agent-cockpit

npm run build
```

Report: `mocked: yes|no`, `live: yes|no`, what was exercised.

---

## 12. Acceptance checklists

### 12.1 Design fixture acceptance (`#battle` design parity mode)

```text
[ ] Shell grid matches DESIGN.md §4 (260 | 1fr | 360)
[ ] Header uses reference mockup scores (8.4 / 7.2) and 3 live-event rows
[ ] Blue strip: 3 fixture patches at reference positions
[ ] Left rail: leader / standing / status density matches reference crops
[ ] Center: .graphWrapHost scroll shell (no shadcn Card in design view)
[ ] 11 design lanes from mockupDesignLanes
[ ] ≥16 marker icons, ≥5 lineage branches (mockup density)
[ ] Playhead overlay present; axis ticks match mockupTimelineTicks() fixture
[ ] Agent detail: 5 fields for selected lane
[ ] Footer: speed, focus, playhead qids present
[ ] verify-data-qid.py → 100%
[ ] verify-battle-ui.sh → all pass (mocked: no, live: yes)
[ ] compare-battle-mockup.py → DOM 13/13, pixel within regression threshold
[ ] battle-design-interactions.json → test-interactions run → 57/57 PASS (mocked: no, live: yes)
[ ] compare-battle-element-captures.py on shell screenshot → E00–E13 crops within threshold
```

### On interaction failure

1. Inspect `results.json` + step screenshots — do not guess from PASS/FAIL alone.
2. Fix code if implementation drifted from DESIGN.md / HTML mockup.
3. Update DESIGN.md (§5/§6/§26) if the authoritative spec changed, then code.
4. Update `battle-design-interactions.json` only if the assertion or inventory was wrong.
5. Re-run verify-battle-ui + compare-battle-mockup + test-interactions; note outcome in DESIGN.md §29.
```



### 12.3 Pixi engine spike acceptance

Full checklist: `BATTLE_RACE_ENGINE_PIXI_SPIKE.md` § Phase 1 acceptance.


```text
[ ] `#battle` default route still uses current DOM/SVG renderer
[ ] `#battle?engine=pixi` mounts BattleRacePixiSpike
[ ] Existing React shell remains visually unchanged
[ ] Pixi mounts only inside `.graphWrapHost`
[ ] DOM graphTitleBar, Blue strip, overview, axis, and sticky labels remain
[ ] Pixi world starts to the right of --label-w: 290px
[ ] Time domain derives from fixture `timeline_control.time_domain`
[ ] Playhead derives from `clock.current_seconds`
[ ] Event x positions derive from event/segment `at_seconds`, `start_seconds`, `end_seconds`
[ ] No backend pixel x values are consumed
[ ] mockupDesignLanes render in design_fixture mode
[ ] one receipt-backed sparse fixture renders in receipt_replay mode
[ ] sparse receipt fixture stays sparse
[ ] parent-child branch appears only after lineage event
[ ] block effect plays only after Blue/Judge receipt
[ ] killed effect plays only after Judge kill receipt
[ ] fastest_crash effect plays only after crash proof + timing receipt
[ ] promoted effect plays only after promotion receipt
[ ] provisional live segments render pending/dashed/dim, not terminal
[ ] DOM hit-target mirrors exist for selectable lanes/events/outcomes
[ ] qid verification includes mirror targets
[ ] Agent Detail updates from Pixi/DOM mirror selection
[ ] deterministic screenshot mode freezes particles/time
[ ] `npm run build` passes
```


### 12.2 Receipt-backed acceptance (truth mode)

```text
[ ] Fixture generated from receipts — not hand-authored UI data
[ ] isBattleDesignView() is false on the route under test
[ ] No child lane without parent + child receipt ids in fixture
[ ] No fastest_crash without crash proof + timing receipt
[ ] No promoted without promotion receipt
[ ] No killed without kill/Judge receipt
[ ] No blocked_handoff / spawn branch without handoff receipt
[ ] Docker replay CTA only when lane.replay metadata exists
[ ] Sparse receipts → sparse UI (no mockup density padding)
[ ] Elapsed-axis placement uses timeline_elapsed_axis_model when enabled
```


## 12.4 Pixi implementation guidance

Before implementing `BattleRaceEngine` or `BattleRacePixiSpike`, use the official PixiJS router:

```bash
npx skills add https://github.com/pixijs/pixijs-skills
```

Then apply the local Battle Pixi overlay skill:

```text
$best-practices-battle-pixi
```

The `$pixijs` router defines generic Pixi v8 patterns and routes to nested API subskills under `skills/pixijs/skills/pixijs-*`.
The Battle Pixi overlay defines project constraints: receipt truth, DOM/Pixi split, qid mirrors, fixed gutter, deterministic screenshots, and no fake terminal effects.


---

## 13. Related paths

| Asset | Path |
|-------|------|
| Full DESIGN.md | `pi-mono/packages/ux-lab/src/components/battle/dual-agent/DESIGN.md` |
| Receipt truth handoff | `skills/battle/docs/BATTLE_004_DESIGN_HANDOFF.md` |
| HTML mockup | `skills/battle/mockups/battle-004-shell-preserving-scroll-timeline.html` |
| Interaction manifest | `pi-mono/packages/ux-lab/src/components/battle/dual-agent/battle-design-interactions.json` |
| Race engine overview | `pi-mono/packages/ux-lab/src/components/battle/dual-agent/BATTLE_RACE_ENGINE.md` |
| **Pixi Phase 1 spike contract** | `pi-mono/packages/ux-lab/src/components/battle/dual-agent/BATTLE_RACE_ENGINE_PIXI_SPIKE.md` |
| Battle Pixi overlay skill | `agent-skills/skills/best-practices-battle-pixi/SKILL.md` |
| Official PixiJS router | `agent-skills/skills/pixijs` → `experiments/pixijs-skills/skills/pixijs`; nested API subskills under `skills/pixijs/skills/pixijs-*` |
| Backend/UX contract | `pi-mono/packages/ux-lab/src/components/battle/dual-agent/BACKEND_UX_CONTRACT.md` |
