# BATTLE-004 Spectator UI — Design Specification

| Field | Value |
|-------|-------|
| **Version** | 2.7 (2026-07-06) |
| **Status** | Authoritative implementation target |
| **Package** | `pi-mono/packages/ux-lab/src/components/battle/dual-agent/` |
| **Route** | `#battle` |
| **Viewport** | 1672×941 (`BATTLE_MOCKUP_VIEWPORT`) |

---

## Table of contents

1. [Purpose](#1-purpose)
2. [View modes](#2-view-modes)
3. [Technology stack](#3-technology-stack)
4. [Shell architecture](#4-shell-architecture)
5. [Region specifications](#5-region-specifications)
6. [State & interactions](#6-state--interactions)
7. [Data contracts](#7-data-contracts)
8. [Lane fixture catalog](#8-lane-fixture-catalog)
9. [Event band partition](#9-event-band-partition)
10. [Timeline coordinate system](#10-timeline-coordinate-system)
11. [CSS architecture](#11-css-architecture)
12. [Color & typography](#12-color--typography)
13. [Icons & Lucide mapping](#13-icons--lucide-mapping)
14. [Data attributes (`data-qid`)](#14-data-attributes-data-qid)
15. [Routes & harnesses](#15-routes--harnesses)
16. [Verification](#16-verification)
17. [Anti-patterns](#17-anti-patterns)
18. [Receipt migration path](#18-receipt-migration-path)
19. [Complete file index](#19-complete-file-index)
20. [Implementation delta (HTML vs React)](#20-implementation-delta-html-vs-react)
21. [Finish status](#21-finish-status)
22. [Glossary](#22-glossary)
23. [Related documents](#23-related-documents)
24. [Agent implementation workflow](#24-agent-implementation-workflow)
25. [Visual reference index](#25-visual-reference-index)
26. [Element catalog](#26-element-catalog)
27. [Animation & motion registry](#27-animation--motion-registry)
28. [Interaction testing (`test-interactions`)](#28-interaction-testing-test-interactions)
30. [Backend / UX contract](#30-backend--ux-contract)
32. [Race engine (Pixi)](#32-race-engine-pixi)
33. [Engine migration (optional renderer)](#33-engine-migration-optional-renderer)
31. [Changelog](#31-changelog)

---

## Authority hierarchy

When documents conflict, follow this order:

1. **HTML mockup** — `agent-skills/skills/battle/mockups/battle-004-shell-preserving-scroll-timeline.html` (structure, class names, bands, copy)
2. **Reference PNG** — `packages/ux-lab/assets/battle-mockup/reference.png` (visual regression guard)
3. **This file (`DESIGN.md`)** — React mapping, stack rules, data contracts, verification
4. **`BATTLE_004_INTERFACE_IMPLEMENTATION_SPEC.md`** — `agent-skills/skills/battle/docs/BATTLE_004_INTERFACE_IMPLEMENTATION_SPEC.md` (agent-skills index; points here)
5. **`BACKEND_UX_CONTRACT.md`** — clock/events/live transport; backend owns time/receipts, UI owns pixels
6. **`BATTLE_004_DESIGN_HANDOFF.md`** — `agent-skills/skills/battle/docs/BATTLE_004_DESIGN_HANDOFF.md` (receipt truth + UI boundary; do not invent receipt data)
6. **`PROJECT_KNOWLEDGE.md`** — `agent-skills/skills/battle/docs/PROJECT_KNOWLEDGE.md` (orchestration / Tau / Docker; out of scope for spectator chrome)

**Acceptance criterion:** DOM under `.battle-mockup-shell` uses the same element classes and hierarchy as the HTML mockup. Pixel `mean_diff` is a regression guard only, not acceptance.

---

## 1. Purpose

The BATTLE-004 spectator interface is a **DAW/movie-editor style race timeline** for watching autonomous Red exploit agents vs Blue patch agents. The `#battle` route renders a **design-faithful shell** over fixture data that mirrors the HTML mockup's 11-lane worker matrix. Production will later bind the same DOM structure to receipt-backed adapters without changing the visual element vocabulary.

**In scope:** shell layout, header, left rail, center timeline (lanes, markers, lineage, playhead), agent detail pane, legend, footer controls.

**Out of scope:** Tau handoff execution, Docker replay runtime, live WebSocket streams, sidebar chat (separate surface per `PROJECT_KNOWLEDGE.md`).

---

## 2. View modes (fixture modes)

**When truth and visual density conflict, truth wins.** See `agent-skills/.../BATTLE_004_INTERFACE_IMPLEMENTATION_SPEC.md` §Authority precedence.

| Mode | Gate | Lanes | Chrome | Truth claims |
|------|------|-------|--------|--------------|
| **Design parity** | `isBattleDesignView()` → `#battle` or `#battle/isolation` | `mockupDesignLanes` | Mockup HTML classes | Visual regression only — dense mockup state allowed |
| **Receipt-backed** | non-design `#battle*` routes | `receiptBackedFixture.lanes` | shadcn + Tailwind | Only mode for truthful Battle status |

```text
Receipt-backed rule: no event kind without receiptId + proofMode in the active fixture.
Design parity may use mockupDesignLanes for screenshot/compare gates only.
Never copy mockup lanes into receipt mode to pad density.
```

```ts
// lib/battle-mockup-lanes.ts
export function isBattleDesignView() {
  const hash = window.location.hash.split("?")[0];
  return hash === "#battle" || hash === "#battle/isolation";
}
```

`AgentDetailPane` routes design → `MockupAgentDetailPane`; receipt → full receipt pane with tabs.  
`battleLanesForView()` returns `mockupDesignLanes` in design mode.

**Design mode hides:** `BattleToolbar`, `RunnerHud`, shadcn footer controls, receipt-mode campaign pulse.  
**Design mode shows:** `BattleMockupFooter`, `BattleMockupLegend`, mockup class vocabulary throughout.

---

## 3. Technology stack

| Layer | Technology | Role |
|-------|------------|------|
| UI shell | React 19 + TypeScript | Components in `dual-agent/` |
| Shell grid | Tailwind | `battle-mockup-app` padding, column gaps only |
| Design chrome | **`battle-mockup-elements.css`** | All `.battle-mockup-shell .{class}` rules |
| Shared race CSS | `battle-race.css` | Zoom buttons, playhead label, legacy `.battle-*` aliases |
| Functional UI | shadcn/ui | Receipt-mode toolbar, sheets, non-design controls |
| Time → x mapping | **D3** `scaleLinear` | Shared by DOM renderer and Pixi renderer |
| Current design renderer | DOM + SVG + CSS | Default until Pixi parity gates pass |
| Race engine spike | PixiJS v8 + `@pixi/react` + `pixi-viewport` | Behind `#battle?engine=pixi` |
| Icons / DOM markers | Lucide via `battle-icons.tsx` | DOM renderer and Pixi hit-target mirrors |
| Spawn forks (DOM path) | **D3 SVG paths** | `BattleLineageFlow`, `spawn-branch-path.ts` |
| Motion | framer-motion | Receipt-mode lane rows only; **not** design markers |

**Renderer status:** DOM/SVG/CSS `RaceViewport` is default. `BattleRacePixiSpike` / `BattleRaceEngine` is optional behind `#battle?engine=pixi` until parity gates pass.

**Canvas/Pixi** is allowed only inside the center race-world body — not for cockpit shell, qid controls, sticky labels, Agent Detail, or accessibility mirrors.

### Forbidden (do not reintroduce)

| Library | Was used for | Replacement |
|---------|--------------|-------------|
| `dnd-timeline` | time→pixel mapping | D3 `scaleLinear` |
| `@xyflow/react` | spawn fork edges | D3 SVG `path` in `BattleLineageFlow` |
| shadcn `Button`/`Badge` | design-view header, rail, lanes, detail | plain mockup classes |
| framer-motion | design-view marker pulse | static `.markerIcon` |
| backend-owned pixel coordinates | server-driven layout | D3 scale in UI only |
| Pixi-only qid testing | canvas coordinate CDP | DOM hit-target mirrors |

---

## 4. Shell architecture

```
.battle-mockup-app                          padding 16px, radial bg
└── .battle-mockup-shell                    max-width 1672px; grid rows:
    ├── row 1  .topbar                      118px  BattleHeader
    ├── row 2  .battle-mockup-main            1fr    grid 260px | 1fr | 360px
    │   ├── .leftRail                       SpectatorRail
    │   ├── .center / .battle-mockup-panel  RaceViewport (+ BlueControlStrip inside)
    │   └── .right                          MockupAgentDetailPane
    ├── row 3  .footerLegend                34px   BattleMockupLegend
    └── row 4  .footer                      64px   BattleMockupFooter
```

HTML mockup uses `.main` for the 3-column row; React uses `.battle-mockup-main` with equivalent grid.

### Layout constants (`lib/layout-constants.ts`)

| Constant | px | CSS variable | Usage |
|----------|-----|--------------|-------|
| `BATTLE_LANE_LABEL_PX` | 290 | `--label-w` | Lane label column, axis corner, blue strip grid |
| `BATTLE_MOCKUP_LEFT_RAIL_PX` | 260 | `--rail-w` | Left rail width |
| `BATTLE_MOCKUP_AGENT_PANE_PX` | 360 | `--detail-w` | Agent detail width |
| `BATTLE_MOCKUP_HEADER_PX` | 118 | — | Header row height |
| `BATTLE_MOCKUP_LEGEND_PX` | 34 | — | Legend row |
| `BATTLE_MOCKUP_FOOTER_PX` | 64 | — | Footer row |
| `BATTLE_MOCKUP_LANE_ROW_ROOT_PX` | 92 | `--row-h-root` | Root lane row |
| `BATTLE_MOCKUP_LANE_ROW_CHILD_PX` | 86 | `--row-h-child` | Child lane row |

### Panel chrome

`.battle-mockup-panel` — border `rgba(90,173,255,.1)`, radius 20px, gradient background, blur. Applied to left rail, center card, agent pane.

---

## 5. Region specifications

### 5.1 Header — `.topbar`

**Component:** `BattleHeader.tsx` (design branch)  
**Grid:** `minmax(340px,1fr) 250px minmax(360px,1fr)` · gap 16px · min-height 118px

```
.topbar
├── .headerBlock
│   ├── .title
│   │   ├── h1          "BATTLE-004 · POST /api/import-zip"
│   │   └── p           CWE-22 Zip Slip · tagline (.dim separators)
│   └── .metaInline
│       ├── Arena       ZIP_SLIP_LAB
│       ├── Objective   Prevent archive path traversal
│       ├── Target      POST /api/import-zip
│       ├── Difficulty  HIGH
│       └── .roundClock Round Time 10:14 / 20:00
├── .score.battle-score-block
│   ├── .scoreSide.red
│   │   ├── .scoreLabel       RED TEAM
│   │   └── .scoreValueRow
│   │       ├── .scoreIcon    Bug
│   │       └── .scoreNum     8.4
│   ├── .vs                   VS
│   └── .scoreSide.blue
│       ├── .scoreLabel       BLUE TEAM
│       └── .scoreValueRow
│           ├── .scoreNum     7.2
│           └── .scoreIcon    Shield
└── .liveEvents.battle-live-events
    ├── .liveEventsHead       dot.red + LIVE EVENTS
    └── .liveEventRow × 3
        ├── .leTime           HH:MM:SS monospace
        ├── .leIcon.{green|blue}
        └── .leText           prefix + b.green|b.blue highlight
```

**Fixture data:** `lib/mockup-design-fixture.ts`

| Export | Design values |
|--------|---------------|
| `mockupArenaLabel()` | `ZIP_SLIP_LAB` |
| `mockupDifficultyLabel()` | `HIGH` |
| `mockupHeaderClock()` | elapsed `10:14`, allotted `20:00` |
| `mockupScoreboard()` | red `8.4`, blue `7.2` |
| `mockupLiveEvents` | 3 rows (see table below) |

**Live event rows (exact copy):**

| Time | Icon | Tone | Text |
|------|------|------|------|
| 10:14:32 | rocket | green | Replay Fork reaches **FASTEST CRASH** |
| 10:14:18 | shield | green | Boundary Fray D promoted to **SURVIVOR** |
| 10:13:55 | shield | blue | Blue deployed **CanonGuard patch** |

**Legacy test hooks:** `.battle-score-block`, `.battle-live-events`, `.battle-live-event-row` must remain on the same nodes as mockup classes.

---

### 5.2 Left rail — `.leftRail`

**Component:** `SpectatorRail.tsx`

```
.leftRail.battle-mockup-panel
├── .railBlock
│   ├── .railHead           Race Leaders
│   └── .leaderItem × 3
│       ├── .rank.r1|r2|r3
│       ├── div
│       │   ├── .liName
│       │   └── .liGen      Gen N
│       └── .liRight        icon + time
├── .railBlock
│   ├── .railHead           Team Standings
│   ├── .standRow.red
│   └── .standRow.blue
└── .railBlock
    ├── .railHead           Agent Status
    └── .statusRow × 6
```

**Fixture:** `mockupRaceLeaders`, `mockupScoreboard()`, `mockupAgentStatus`

**Selection:** `selectedId` prop → `.leaderItem.selected` (default `payload-857-A`)

| Rank | Lane | Name | Time | Status icon |
|------|------|------|------|-------------|
| 1 r1 | payload-857-A | Replay Fork | 10:14.32 | rocket / fastest_crash |
| 2 r2 | payload-912-D | Boundary Fray D | 10:12.18 | shield-check / promoted |
| 3 r3 | payload-912-B | Boundary Fray B | 10:11.02 | shield-x / blocked |

---

### 5.3 Center — `.center`

**Component:** `RaceViewport.tsx` (orchestrator) inside `.battle-mockup-panel.battle-mockup-center`

#### 5.3.0 Center shell (HTML authority)

```
.center
├── .blueStripCenter
├── .graphTitleBar
├── .timelineOverview
└── .graphWrapHost
    ├── DOM renderer path (current default)
    │   └── .graphWrap              horizontal scroll container
    │       └── .graph
    │           └── .timelineShell
    │               ├── .axis
    │               │   ├── .axisCorner     TIME
    │               │   └── .axisTrack
    │               │       ├── .ticks
    │               │       └── .stage      5-column stage row
    │               ├── .rows               lane rows
    │               └── .playheadOverlay
    ├── Pixi renderer path (`#battle?engine=pixi` spike only)
    │   └── BattleRaceEngine
    │       ├── BattleRacePixiStage
    │       ├── BattlePixiTrackLayer
    │       ├── BattlePixiRunnerLayer
    │       ├── BattlePixiLineageLayer
    │       ├── BattlePixiEffectsLayer
    │       ├── BattlePixiPlayheadLayer
    │       └── BattlePixiHitTargetMirrorLayer   DOM overlay
    └── .graphScrollHint            "More outcomes →"
```

React maps `.graphWrapHost` / `.graphWrap` / `.graph` / `.timelineShell` via `battle-mockup-elements.css` and `RaceViewport` design branch. The Pixi renderer must mount inside the same `.graphWrapHost` bounds and preserve outer shell geometry. `[data-battle-timeline-track]` is the ResizeObserver anchor for D3 scale width.

#### 5.3.1 Blue control strip

**Component:** `BlueControlStrip.tsx`

```
.blueStripCenter.battle-blue-strip
├── .blueStripLabel
│   ├── .stripIconBox
│   ├── .stripTitle / .stripSub
│   └── .blueStat          Interventions 4 · Blocks 2
└── grid [290px | 1fr]
    ├── (spacer)
    └── .bluePatchRow
        └── .bluePatch × 3
            ├── Shield icon 14px
            ├── label
            └── .bpSub       timestamp
```

**Patch positions (track %):** 18 → CanonGuard v1 `10:06:12`, 42 → PathSanity Patch `10:08:47`, 68 → Boundary Shield `10:11:23`

#### 5.3.2 Graph title bar

**Component:** `RaceViewport.tsx` — class `.graphTitleBar`

- Title: `Evolution & Progress Graph`
- `.zoomHint` · Zoom `N%`
- `.zoomBtns` / `.zoomBtn` − +
- `.playheadLabel` PLAYHEAD 10:14:32

#### 5.3.3 Timeline overview

**Component:** `TimelineOverview.tsx`

**HTML authority:**

```
.timelineOverview
├── .overviewSpacer          290px label column
├── .overviewTrackWrap
│   └── .overviewTrack
│       ├── .overviewViewport   scroll window handle (synced to graphWrap scroll)
│       └── .overviewMark.{crash|promoted|blocked}   left: N%
└── .scrollHint              "More outcomes →"
```

**Overview marks (fixture):**

| Class | left % | title |
|-------|--------|-------|
| `.overviewMark.crash` | 77 | Replay Fork · fastest crash |
| `.overviewMark.promoted` | 88 | Boundary Fray D · promoted |

**Current React delta:** uses `.battle-overview-mark.battle-overview-mark-{tone}` with equivalent CSS in `battle-race.css`. Rename to `.overviewMark` when touching overview (see §20).

Marks are derived from `overviewMarksFromLanes()` in `timeline-playback.ts` (terminal events: fastest_crash, promoted, blocked).

#### 5.3.4 Timeline axis

**Component:** `BattleTimelineAxis.tsx`

**HTML authority:**

```
.axis
├── .axisCorner               TIME (290px column)
└── .axisTrack
    ├── .ticks                wall clock labels 10:04…10:14
    └── .stage                  5 equal columns, 34px height
        └── div × 5             icon + Research | Payload | Mutate | Retry | Terminal
```

**Stage row CSS (HTML):** `.stage{display:grid;grid-template-columns:repeat(5,1fr);height:34px;…}`

**Current React delta:** stage row uses Tailwind `grid grid-cols-5` inside `.battle-timeline-axis` instead of `.stage` wrapper (see §20). Tick labels use `.font-mono` (isolation harness selector).

Design mode: 2-column grid (`290px | 1fr`). Corner label reads `Time` (HTML: `TIME`).

#### 5.3.5 Lane rows

**Component:** `LaneRow.tsx` (design early-return branch)

```
.row.{root|child}.{purple?}.{childIndent?}.{selected?}
├── .labelCell
│   ├── .chev              › ⌄ or empty
│   ├── .laneIcon          Bug (root) | GitBranch (child)
│   ├── .labelText
│   │   ├── .name
│   │   └── .payload
│   └── .gen[.g2]
└── .track[data-lane-track]
    ├── .trackGrid
    ├── .laneTop           .phaseLabel.top
    ├── .laneMidAbove      .token.labelOnly.above
    ├── .laneCenter
    │   ├── .line.{red|green|purple}
    │   └── .markerIcon.*
    └── .laneBottom        .phaseLabel.bottom[.blue|.green|.yellow]
```

**Row height:** root 92px, child 86px. **Collapse:** parent `hasChildren` → chevron toggles `collapsed` set in `RaceViewport`. Default: `payload-912` expanded (children visible).

#### 5.3.6 Playhead

**Component:** `BattlePlayheadCursor.tsx` inside `.playheadOverlay` grid

```
.playheadOverlay              grid: 290px | 1fr
├── (spacer)
└── .playheadTrack
    └── .playhead.battle-playhead
```

Playhead at mockup T+23.1 → wall clock `10:14:32`. Hidden `.battle-playhead-line` retained for isolation harness.

#### 5.3.7 Lineage

**Component:** `BattleLineageFlow.tsx` — SVG overlay, green stroke `rgba(60,240,122,.55)`

Path geometry (`spawn-branch-path.ts`): vertical at parent handoff X, horizontal into child lane entry.

**Expected branches:** 5 (payload-857→857-A, payload-912→912-A/B/C/D)

---

### 5.4 Agent detail — `.right`

**Component:** `MockupAgentDetailPane.tsx` via `AgentDetailPane.tsx` router

```
.right.battle-mockup-agent-pane
├── .detailHead
│   ├── .paneLabel
│   └── .detailClose
├── .agentTitleRow
│   ├── .agentBug
│   └── .agentName / .agentMeta
├── .agentPayload              lane.payloadId (monospace)
├── .agentHeroBadges           .statusPill (fastest_crash only)
├── .dockerReplay.dockerReplayTop   if lane.replay
└── .detailBody.detailScroll
    ├── .field Status          .statusPillInline + dot
    ├── .field Current Loop    .loopGrid 3-col
    ├── .field Inherited       .kvGrid
    ├── .field Mutation        .mutBox
    └── .field Latest Receipt  .receiptBlock (pre-wrap monospace)
```

**Default selection fixture (`payload-857-A`):**

| Field | Value |
|-------|-------|
| Badge | FASTEST CRASH |
| Status | RUNNING · 10:14:32 |
| Loop stage | TRIGGER |
| Parent | Archive Escape (Gen 1) |
| Handoff | ZIP_SLIP_CONFIRMED |
| Receipt | `payload-857-A-replay` / FASTEST_CRASH_CONFIRMED / SIGSEGV @ validate_path() |

**Docker replay lanes:** `payload-857`, `payload-857-A`, `payload-912-D` (`hasReplay: true` in mock specs)

Non-default lanes fall back to `mockupAgentDetail()` generic template (status from `lane.terminal`).

---

### 5.5 Legend — `.footerLegend`

**Component:** `BattleMockupLegend` in `BattleSpectatorArena.tsx`

Items: — Exploit Progress (red), Blue Intervention, Blocked (Handoff), Killed, Useful Signal, Promoted/Survivor, Fastest Crash — with inline Lucide icons and mockup colors.

---

### 5.6 Footer — `.footer`

**Component:** `BattleMockupFooter.tsx`

```
.footer
├── .liveBadge              Spectator Mode · LIVE/ARM
├── .footerControls
│   ├── .playback           SPEED 1x 2x 4x 8x (.footChip)
│   ├── .focusChips         FOCUS All Lanes | Red Team | Blue Team
│   └── .playback           VIEW ☰ ▥ ▦
└── .fit                    playhead toggle
```

**Focus filter mapping (HTML `data-filter`):** `all` | `root` (Red Team / gen 1) | `gen2` (Blue Team / gen 2 children).

---

## 6. State & interactions

Mirrors HTML mockup script state (`MAX_T=30`, `PLAYHEAD_T=23.1`).

| State | Owner | Default | Behavior |
|-------|-------|---------|----------|
| `selectedId` | `BattleSpectatorArena` | `payload-857-A` | Rail `.leaderItem.selected`, lane `.row.selected`, agent pane content |
| `collapsed` | `RaceViewport` | `{}` | Parent lanes with children hide child rows when lane id in set |
| `filter` | `BattleMockupFooter` | `all` | `all` / `root` / `gen2` lane visibility |
| `zoom` | `RaceViewport` | `1` | Ctrl+wheel, ± buttons; scales `timelineContentWidth` |
| `playing` | footer / arena | `false` | Toggles playhead animation (receipt mode primary) |
| `speed` | footer | `1x` | Playback speed chips |

**Lane click:** `data-qid="battle:lane:{id}"` → selects lane, updates agent pane.  
**Leader click:** `data-qid="battle:leaderboard:item:{laneId}"` → same selection.  
**Collapse:** chevron on parent row toggles `collapsed` without deselecting.  
**Scroll sync:** `graphWrap` horizontal scroll ↔ `.overviewViewport` width/left.  
**Zoom:** does not change mockup T domain; scales pixel width of timeline content.

---

## 7. Data contracts

Types live in `lib/battle-types.ts`. Design view consumes `Lane` + fixture helpers; receipt view consumes `BattleNormalizedUxFixture`.

### `Lane` (design-critical fields)

| Field | Type | Design usage |
|-------|------|--------------|
| `id` | string | Row key, selection, `data-lane-id` |
| `name` | string | `.name` label |
| `payloadId` | string | `.payload` monospace |
| `generation` | number | `.gen` / `.gen.g2` |
| `parentId` | string? | Child indent, lineage |
| `children` | string[]? | Collapse chevron, lineage targets |
| `xStart`, `xEnd` | number | Track % 0–100 for line span |
| `lineColor` | red\|green\|purple | `.line.{color}` |
| `terminal` | LaneTerminal | Marker tone, overview marks |
| `events` | LaneEvent[] | Partitioned into four bands |
| `replay` | BattleReplayRef? | Docker CTA visibility |
| `inheritedContext` | string[]? | Agent detail handoff field |

### `LaneEvent` (design-critical fields)

| Field | Type | Design usage |
|-------|------|--------------|
| `id` | string | Must encode band: `:top:`, `:bottom:`, `:above:`, `:icon:` |
| `kind` | LaneEventKind | Marker icon + tone mapping |
| `x` | number | Track % position |
| `label` | string? | Phase label or token text |

### Event ID encoding (required for partition)

```
{id}:top:{index}      → .laneTop
{id}:bottom:{index}   → .laneBottom
{id}:above:{index}    → .laneMidAbove
{id}:icon:{index}     → .laneCenter .markerIcon
{id}:spawn            → handoff marker (center)
```

Produced by `phasesToEvents`, `aboveToEvents`, `iconsToEvents` in `battle-mockup-lanes.ts`.

### `MockupLiveEvent` (header ticker)

```ts
{ id, time, icon, iconTone, prefix, highlight, highlightTone }
```

### Receipt adapter contract (future)

Receipt lanes mapped to `Lane` must preserve event ID suffixes so `partitionMockupLaneEvents()` works unchanged. Do not flatten events into a single band.

---

## 8. Lane fixture catalog

All design lanes from `lib/battle-mockup-lanes.ts` (`MOCK_SPECS` → `mockupDesignLanes`). Timeline domain T=0…30 → track % 0…100 via `mockupT(t)`.

| ID | Name | Gen | Parent | Line | Terminal | Children |
|----|------|-----|--------|------|----------|----------|
| payload-857 | Archive Escape | 1 | — | red | useful_killed | 857-A |
| payload-857-A | Replay Fork | 2 | 857 | green | fastest_crash | — |
| payload-231 | Tar Tunnel | 1 | — | red | killed | — |
| payload-404 | DotDot Drip | 1 | — | red | killed | — |
| payload-118 | Symlink Shuffle | 1 | — | red | killed | — |
| payload-620 | Boundary Nudge | 1 | — | red | killed | — |
| payload-912 | Boundary Fray | 1 | — | red | useful_killed | A,B,C,D |
| payload-912-A | Boundary Fray A | 2 | 912 | purple | killed | — |
| payload-912-B | Boundary Fray B | 2 | 912 | purple | blocked | — |
| payload-912-C | Boundary Fray C | 2 | 912 | purple | killed | — |
| payload-912-D | Boundary Fray D | 2 | 912 | purple | promoted | — |

**Default selected lane:** `payload-857-A` (`mockupDefaultSelectedLaneId`)

### Per-lane events (T units → bands)

| Lane | Top phases | Above tokens | Center icons | Bottom phases |
|------|------------|--------------|--------------|---------------|
| payload-857 | RESEARCH@3, PAYLOAD@8, TRIGGER@12 | USEFUL@10.8 | shield@20.4 | KILLED@20.4 |
| payload-857-A | MUTATE@21.2, INHERIT@22, SEND@22.8 | — | rocket@23.1 | FASTEST CRASH@24.5 |
| payload-231 | RESEARCH@1.5, PAYLOAD@3 | — | skull@5.8 | KILLED@5.8 |
| payload-404 | RESEARCH@4, PAYLOAD@8, TRIGGER@11 | — | shieldx@13, skull@14.8 | KILLED@15.5 |
| payload-118 | RESEARCH@6, PAYLOAD@12, OBSERVE@16 | — | shieldx@18.9, skull@21.2 | KILLED@21.2 |
| payload-620 | RESEARCH@8, PAYLOAD@14, RETRY@20 | — | shield@24.6, skull@27 | KILLED@27 |
| payload-912 | RESEARCH@4, PAYLOAD@9, TRIGGER@14 | LEAK@11.4, SPAWN@19.8 | skull@18.7 | KILLED@18.7 |
| payload-912-A | MUTATE@19.2, RETRY@20.4 | — | skull@20.6 | KILLED@20.6 |
| payload-912-B | MUTATE@19.2, TRIGGER@20.5 | — | shieldx@19.5 | BLUE BLOCK@19.5 |
| payload-912-C | MUTATE@19.5, RETRY@21.2 | — | skull@24.1 | KILLED@24.1 |
| payload-912-D | MUTATE@19.5, RETRY@22.2, OBSERVE@25.5 | — | rocket@28.4 | PROMOTED@28.4 |

**Spawn branches:** 857@20.4→857-A; 912@19.8→912-A/B/C/D.

---

## 9. Event band partition

**Partition:** `lib/mockup-lane-partition.ts` → `partitionMockupLaneEvents(lane)`

| Suffix / kind | DOM band | Element class |
|---------------|----------|---------------|
| `:top:` | `.laneTop` | `.phaseLabel.top` |
| `:above:` | `.laneMidAbove` | `.token.labelOnly.above` + `tokYellow|tokGreen` |
| `:icon:` or icon kinds | `.laneCenter` | `.markerIcon` + tone |
| `:bottom:` | `.laneBottom` | `.phaseLabel.bottom` + optional tone class |

### Marker taxonomy (`mockupMarkerClasses`)

| Event kind | Classes | Icon |
|------------|---------|------|
| useful | `markerIcon tokYellow` | Lightbulb |
| blocked, blue_blast, detected | `markerIcon tokBlue terminal` | ShieldX / Radar |
| killed | `markerIcon tokRed terminal` | Skull |
| fastest_crash | `markerIcon tokGreen terminal big` | Rocket |
| promoted | `markerIcon tokGreen terminal big` | ShieldCheck |
| handoff | `markerIcon tokPurple` | GitBranch |

**Icon event kinds** (`layout-lane-events.ts`): blocked, killed, promoted, fastest_crash, handoff, blue_blast, detected.

### Bottom phase tone classes

| Label contains | Class |
|----------------|-------|
| BLOCK, PATCH, GATE, BLUE | `.bottom.blue` |
| PROMOT, CRASH | `.bottom.green` |
| SPAWN, RECEIPT | `.bottom.yellow` |

---

## 10. Timeline coordinate system

```
Mockup T domain:     0 ─────────────── 30  (MAX_T in HTML)
Track percent:       0 ─────────────── 100 (lane.xStart, lane.xEnd, event.x)
Wall clock:          10:04 ─────────── 10:14 (MOCKUP_CLOCK_START + 10min span on axis)
Playhead:            T=23.1 → 10:14:32
Allotted seconds:    600 (10 min) — mockupPlayheadSeconds()
Header round clock:  10:14 / 20:00 (fixture static; not tied to T domain)
```

**D3 scale** (`BattleTimelineProvider`):

- `ResizeObserver` on `[data-battle-timeline-track]` → `trackWidth`
- Design view: `laneTrackWidth = trackWidth - 290` (label column excluded)
- `leftPxFromLaneX(x)` = `scaleLinear([0, allottedMs], [0, laneTrackWidth])(x/100 * allottedMs)`
- All markers, patches, playhead, axis ticks share this scale

**Zoom:** `timeline-playback.ts` — `timelineContentWidth(zoom)`, Ctrl+wheel, step zoom buttons. Default zoom 1.

**Tick positions:** `mockupTimelineTicks()` → x% 0, 20, 40, 60, 80, 100 → labels 10:04…10:14.

---

### Pixi timeline rendering rules

Backend emits seconds; UI derives x via shared D3 scale. Pixi coordinates are track-plane relative. Fixed 290px gutter; DOM labels sticky; Pixi tracks/effects only right of gutter. Child lanes at spawn time; branches after lineage receipt; terminals after Judge receipt; provisional motion visually distinct.

---

## 11. CSS architecture

| File | Imported by | Purpose |
|------|-------------|---------|
| `battle-race.css` | `BattleSpectatorArena.tsx` | Legacy `.battle-*`, zoom/playhead, overview grid helpers |
| `battle-mockup-elements.css` | `BattleSpectatorArena.tsx` | **Authoritative** mockup rules under `.battle-mockup-shell` |

**Import order:** `battle-race.css` then `battle-mockup-elements.css` (mockup wins on specificity conflicts).

**Rule:** New design-view styles go in `battle-mockup-elements.css` as `.battle-mockup-shell .{class}`. Do not add Tailwind to design-view semantic elements.

### Mockup class registry (`battle-mockup-elements.css`)

`agentBug`, `agentHeroBadges`, `agentMeta`, `agentName`, `agentPayload`, `agentTitleRow`, `bluePatch`, `bluePatchRow`, `blueStat`, `blueStripCenter`, `blueStripLabel`, `chev`, `childIndent`, `detailBody`, `detailClose`, `detailHead`, `detailScroll`, `dim`, `dockerReplay`, `dockerReplayTop`, `dot.red`, `field`, `footerLegend`, `gen`, `gen.g2`, `graphTitleBar`, `headerBlock`, `kvGrid`, `labelCell`, `laneBottom`, `laneCenter`, `laneIcon`, `laneMidAbove`, `laneTop`, `leaderItem`, `leaderItem.selected`, `leftRail`, `leIcon`, `leIconSvg`, `leText`, `leTime`, `line`, `liveEventRow`, `liveEvents`, `liveEventsHead`, `loopGrid`, `markerIcon`, `metaInline`, `mutBox`, `name`, `paneLabel`, `payload`, `phaseLabel`, `playhead`, `playheadOverlay`, `playheadTrack`, `railBlock`, `railHead`, `receiptBlock`, `right`, `roundClock`, `row`, `score`, `scoreIcon`, `scoreLabel`, `scoreNum`, `scoreSide`, `scoreValueRow`, `standIcon`, `standName`, `standRow`, `standScore`, `standSub`, `statusPill`, `statusPillInline`, `statusRow`, `stripSub`, `stripTitle`, `title`, `tokBlue`, `tokGreen`, `tokPurple`, `tokRed`, `tokYellow`, `token.labelOnly`, `topbar`, `track`, `trackGrid`, `vs`

### HTML-only classes (in mockup, styled in `battle-race.css` or pending)

`axis`, `axisCorner`, `axisTrack`, `ticks`, `stage`, `rows`, `graph`, `graphWrap`, `graphWrapHost`, `graphScrollHint`, `overviewMark`, `overviewSpacer`, `overviewTrack`, `overviewTrackWrap`, `overviewViewport`, `scrollHint`, `timelineOverview`, `timelineShell`, `stripIconBox`, `bpSub`, `footChip`, `footer`, `footerControls`, `liveBadge`, `fit`, `focusChips`, `playback`, `zoomBtn`, `zoomBtns`, `playheadLabel`, `zoomHint`, `app`, `main`, `center`

Lineage: `.battle-lineage-branch` / `.battle-lineage-svg` (green stroke in design shell)

### Legacy test aliases (must coexist)

| Mockup class | Legacy alias | Used by |
|--------------|--------------|---------|
| `.score` | `.battle-score-block` | isolation + compare |
| `.liveEvents` | `.battle-live-events` | isolation |
| `.liveEventRow` | `.battle-live-event-row` | compare |
| `.blueStripCenter` | `.battle-blue-strip` | isolation |
| `.bluePatch` | `.battle-blue-patch` | compare |
| `.playhead` | `.battle-playhead` | isolation |
| — | `.battle-playhead-line` | isolation (hidden in design) |

---

### Pixi host CSS

```css
.battleRaceStageHost { position: relative; min-width: 0; min-height: 0; width: 100%; height: 100%; overflow: hidden; }
.battleRacePixiCanvas { position: absolute; inset: 0; width: 100%; height: 100%; }
.battlePixiHitMirrorLayer { position: absolute; inset: 0; pointer-events: none; z-index: 30; }
.battlePixiHitMirror { position: absolute; pointer-events: auto; opacity: 0; border: 0; background: transparent; }
```

Pixi world-space: `screenX = labelWidthPx + timeScale(at_seconds)` with `--label-w: 290px`.

---

## 12. Color & typography

### CSS variables (HTML `:root` → use in design)

| Token | Hex | Usage |
|-------|-----|-------|
| `--green` | `#3cf07a` | Promoted, lineage, survivor, useful survivor |
| `--red` | `#ff4d5c` | Red team, killed, exploit line |
| `--blue` | `#5aadff` | Blue team, patches, blocked |
| `--yellow` | `#ffd24d` | Useful signal tokens |
| `--purple` | `#c47aff` | Child lanes, handoff |
| `--cyan` | `#5ee6ff` | Playhead |
| `--muted` | `#6a7d94` | Secondary text |
| `--label-w` | `290px` | Label column |
| `--row-h-root` | `92px` | Root lane height |
| `--row-h-child` | `86px` | Child lane height |

### Typography scale (mockup)

| Element | Size | Weight | Notes |
|---------|------|--------|-------|
| `.title h1` | 24px | 700 | Gradient fill #fff→#b4d0ec |
| `.title p` | 12.5px | 500 | `#7a8fa8` |
| `.metaInline` | 11px | — | `#5a6e85`, bold labels `#8a9eb8` |
| `.scoreNum` | 26px | 800 | |
| `.liveEventRow` | 11.5px | — | line-height 1.35 |
| `.leTime` | 11px | — | monospace |
| `.name` | 13px | 700 | uppercase |
| `.payload` | 10px | 500 | monospace |
| `.phaseLabel` | 8px | 800 | uppercase, letter-spacing .04em |
| `.agentName` | 26px | 800 | |
| `.field label` | 11px | 600 | uppercase |
| `.receiptBlock` | 11px | — | monospace, line-height 1.6 |
| `.stage div` | 9.5px | 700 | uppercase, letter-spacing .06em |

**Font stack:** `Inter`, `SF Pro Display`, `ui-sans-serif`, `system-ui`, sans-serif

---

## 13. Icons & Lucide mapping

HTML mockup `icon` object → `battle-icons.tsx` (`Icons.*`):

| Mockup key | Lucide | Usage |
|------------|--------|-------|
| root | `Bug` | Root lane `.laneIcon` |
| branch | `GitBranch` | Child lane `.laneIcon` |
| bulb | `Lightbulb` | useful marker |
| skull | `Skull` | killed marker |
| shield | `Shield` | blue patch, blocked |
| shieldx | `ShieldX` | blocked terminal |
| rocket | `Rocket` | fastest_crash / promoted |
| receipt | `FileJson` | receipt mode only |

Stage row: `Search`, `Code2` (Payload), `Dna`, `RefreshCw`, `Terminal`.

Live events: row 1 rocket; rows 2–3 shield (not shield-check in design DOM).

---

## 14. Data attributes (`data-qid`)

Harness and QuickStart actions use `data-qid` / `data-qs-action`. Design-critical selectors:

| Attribute | Example | Region |
|-----------|---------|--------|
| `data-lane-row` | — | Lane row count (11) |
| `data-lane-id` | `payload-857-A` | Lane identity |
| `data-lane-track` | — | Track width / lineage geometry |
| `data-battle-timeline-track` | — | D3 ResizeObserver root |
| `data-battle-marker-icon` | — | Center marker count (≥16) |
| `data-battle-marker-label` | — | Phase labels |
| `data-qid` | `battle:lane:{id}` | Lane selection |
| `data-qid` | `battle:agent-pane:{id}` | Agent pane mounted |
| `data-qid` | `battle:leaderboard:item:{id}` | Rail leader row |
| `data-qid` | `battle:marker:{laneId}:{kind}` | Marker hit target |

---

## 15. Routes & harnesses

| Hash | Component | Purpose |
|------|-----------|---------|
| `#battle` | `BattleSpectatorArena` | Production design shell |
| `#battle/isolation` | `BattleComponentIsolationHarness` | Per-component DOM checks (48 tests) |
| `#battle/component-test` | `BattleComponentCapabilityHarness` | D3 timeline + lineage capability (17 tests) |

Entry: `BattleArenaView.tsx` → `BattleSpectatorArena`

**Dev server:**

```bash
cd packages/ux-lab
npx vite --host 127.0.0.1 --port 3012   # if npm run dev hits ENOSPC
```

### Isolation harness components (48 checks)

`battle-header`, `spectator-rail`, `mockup-agent-detail-pane`, `battle-toolbar`, `campaign-pulse`, `timeline-overview`, `battle-timeline-axis`, `battle-playhead-cursor`, `blue-control-strip`, `lane-row`, `lane-event-marker`, `lane-event-label`, `battle-lineage-flow`, `race-viewport`, `battle-mockup-footer`, `battle-mockup-legend` (+ sub-checks each)

---

## 16. Verification

### Scripts

```bash
./scripts/verify-battle-ui.sh          # capability + isolation + compare
python3 scripts/compare-battle-mockup.py # pixel regression + DOM checks
```

### Pixi engine spike acceptance (`#battle?engine=pixi`)

See `BATTLE_004_INTERFACE_IMPLEMENTATION_SPEC.md` §12.3 for full checklist. Default `#battle` must remain DOM/SVG until parity gates pass.

### DOM acceptance checklist (live `#battle`)

| Check | Expected |
|-------|----------|
| `[data-lane-row]` | 11 |
| `[data-battle-marker-icon]` | ≥ 16 |
| `.battle-lineage-svg path` | ≥ 5 |
| `.bluePatch` | ≥ 3 |
| `.liveEventRow` | 2–3 |
| `.battle-score-block` contains `8.4` | true |
| `[data-qid^="battle:agent-pane:"]` | mounted |
| Axis ticks | start `10:04`, includes `10:14` |

### Pixel regression baselines (2026-07-05 live, not acceptance)

| Region | Box (x0,y0,x1,y1) | mean_diff |
|--------|-------------------|-----------|
| overall | 0,0,1672,941 | 10.0 |
| header | dynamic topbar | 11.6 |
| blue_strip | 218,118,1672,190 | 13.3 |
| timeline_axis | 218,190,1672,262 | 16.6 |
| timeline | 218,262,1672,860 | 16.5 |
| left_rail | 0,118,260,860 | 15.0 |
| agent_detail | dynamic main_top | 13.8 |
| footer | 0,860,1672,941 | 9.3 |

Fail threshold: `BATTLE_MOCKUP_BASELINE` (25) + `BATTLE_MOCKUP_REGRESSION_SLACK` (1.5) = 26.5 overall. Region crops under `.artifacts/battle-mockup-compare/regions/`.

### Structural DOM spot-check

```javascript
// Run in browser console at #battle
({
  topbar: document.querySelectorAll('.topbar').length,
  rows: document.querySelectorAll('.row').length,
  phaseLabels: document.querySelectorAll('.phaseLabel').length,
  markerIcons: document.querySelectorAll('.markerIcon').length,
  playheadOverlay: document.querySelectorAll('.playheadOverlay').length,
  fields: document.querySelectorAll('.field').length,
  footerLegend: document.querySelectorAll('.footerLegend').length,
})
// Expected: topbar 1, rows 11, phaseLabels >> 0, markerIcons >> 0, playheadOverlay 1, fields 5, footerLegend 1
```

### Report format

Every implementation report must state:

- `mocked: yes|no`
- `live: yes|no`
- What was exercised (URL, script)
- What remains unverified

**mocked: no · live: yes** required before claiming structural acceptance.

---

## 17. Anti-patterns

| Do not | Do instead |
|--------|------------|
| Invent lanes/events not in fixture | Extend `MOCK_SPECS` or receipt adapter |
| Use xyflow for spawn forks | `BattleLineageFlow` SVG paths |
| Use shadcn Button in design header/rail/lanes | `.footChip`, `.zoomBtn`, plain `<button>` |
| Put research/payload labels in `.laneMidAbove` | `:top:` → `.laneTop` |
| Map scale to full canvas width in design | Subtract 290px label column |
| Claim done on pixel score alone | DOM class parity + live scripts |
| Add dashboard metric cards | Mockup elements only |
| Synthesize fastest_crash/promotion without receipt | Follow `BATTLE_004_DESIGN_HANDOFF.md` |

---

## 18. Receipt migration path

When `receiptBackedFixture` exposes full parent-spawn lineage:

1. **Keep** all mockup class names and DOM structure unchanged
2. **Swap** `battleLanesForView()` to map receipt lanes → same `Lane` shape with `:top:`/`:icon:` event IDs
3. **Replace** `mockupLiveEvents` with last 3 `BattleEvent` rows from receipt stream
4. **Wire** `lane.replay` from `tau.subagent_receipt.v1` docker replay refs
5. **Retain** `isBattleDesignView()` gate until receipt DOM parity proven; then consider single view

Adapter must not synthesize fastest_crash, promotion, or child spawn without receipt proof (`BATTLE_004_DESIGN_HANDOFF.md`).

---

## 19. Complete file index

### Components

| File | Role |
|------|------|
| `BattleSpectatorArena.tsx` | Shell grid, legend, routes footer |
| `BattleHeader.tsx` | `.topbar` |
| `SpectatorRail.tsx` | `.leftRail` |
| `RaceViewport.tsx` | Center orchestration, zoom, scroll, lanes container |
| `BlueControlStrip.tsx` | `.blueStripCenter` |
| `TimelineOverview.tsx` | `.timelineOverview` |
| `BattleTimelineAxis.tsx` | Time axis + stage row |
| `BattleTimelineProvider.tsx` | D3 scale context |
| `LaneRow.tsx` | `.row` design branch |
| `LaneEventMarker.tsx` | `.markerIcon` |
| `LaneEventLabel.tsx` | `.phaseLabel` / `.token` |
| `BattlePlayheadCursor.tsx` | `.playhead` |
| `BattleLineageFlow.tsx` | SVG lineage |
| `AgentDetailPane.tsx` | Design/receipt router |
| `MockupAgentDetailPane.tsx` | `.right` agent detail |
| `BattleMockupFooter.tsx` | `.footer` |
| `RunnerHud.tsx` | Receipt-mode runner only (hidden in design) |

### Libraries

| File | Role |
|------|------|
| `lib/battle-mockup-lanes.ts` | `MOCK_SPECS`, `mockupDesignLanes`, `isBattleDesignView` |
| `lib/mockup-design-fixture.ts` | Header, rail, live events, agent detail constants |
| `lib/mockup-lane-partition.ts` | Event band split, marker class helpers |
| `lib/battle-timeline-scale.ts` | D3 `scaleLinear` factory |
| `lib/spawn-branch-path.ts` | Fork SVG path |
| `lib/layout-lineage-rails.ts` | Branch geometry from row rects |
| `lib/layout-lane-events.ts` | Receipt-mode label layout |
| `lib/timeline-playback.ts` | Zoom, playhead scroll, overview marks |
| `lib/layout-constants.ts` | Shell dimensions |
| `lib/marker-labels.ts` | Phase label text helpers |
| `lib/battle-data.ts` | `battleLanesForView`, fixture imports |
| `lib/battle-types.ts` | All TypeScript contracts |

### Styles

| File | Role |
|------|------|
| `battle-mockup-elements.css` | Mockup class authority (~90 rules) |
| `battle-race.css` | Shared race + legacy aliases |

### Tests & scripts

| File | Role |
|------|------|
| `scripts/verify-battle-ui.sh` | Full live gate |
| `scripts/compare-battle-mockup.py` | PNG diff + DOM |
| `scripts/test-battle-components.py` | 17 capability tests |
| `scripts/test-battle-isolation.py` | 48 isolation tests |

---

## 20. Implementation delta (HTML vs React)

Known deviations tracked for finish work. **Structural acceptance does not require zero delta** if DOM class parity holds for user-visible mockup vocabulary; these are polish targets.

| Item | HTML authority | Current React | Priority |
|------|----------------|---------------|----------|
| Stage row wrapper | `.stage` inside `.axisTrack` | `.stage` in `BattleTimelineAxis` (design) | done |
| Overview marks | `.overviewMark.crash` × 2 fixed | `mockupOverviewMarks()` + legacy alias | done |
| Axis corner label | `TIME` | `TIME` in `.axisCorner` | done |
| Stage icons | inline SVG in HTML | Lucide components | acceptable |
| Main row class | `.main` | `.battle-mockup-main` | acceptable (equivalent grid) |
| App wrapper | `.app` | `.battle-mockup-app` | acceptable |
| Live event icon | inline SVG | `.leIcon` + Lucide | acceptable |
| Center scroll shell | `.center` → `.graphWrapHost` → `.graphWrap` → `.timelineShell` | `RaceViewport` design branch (no shadcn Card) | done |
| Header pixel density | reference PNG | mean_diff ~11.6 | acceptable |
| Agent detail rhythm | reference PNG | mean_diff ~13.8 | acceptable |

**Resolution rule:** When fixing a delta, update both implementation and this table. Remove row when parity achieved.

---

## 21. Finish status

### Complete (structural + documented)

- [x] Stack: React + mockup CSS + D3 (no dnd-timeline/xyflow)
- [x] Shell grid and layout constants
- [x] Header `.topbar` / score / live events
- [x] Left rail leaders, standings, status
- [x] Blue strip patches
- [x] Lane rows four-band layout
- [x] Markers, phases, tokens
- [x] Playhead overlay
- [x] Green lineage SVG
- [x] Agent detail fields
- [x] Legend + footer
- [x] DESIGN.md v1.1 (this document)
- [x] Live verification: 17/17 capability, 48/48 isolation, 13/13 DOM (incl. center shell)
- [x] Center pane `.center` / `.graphWrapHost` / `.timelineShell` HTML scroll shell

### Remaining (visual polish — non-blocking for structure)

- [x] Header region pixel diff → **11.6** (HTML reference, auto topbar height)
- [x] Agent detail receipt rhythm → **13.8** (HTML reference)
- [x] Timeline axis `.stage` row class parity
- [x] Overview `.overviewMark` class + fixed 2-mark fixture

### Remaining (backend — post-visual)

- [ ] Receipt lane adapter with `:top:`/`:icon:` event IDs
- [ ] Live events from `BattleEvent` stream
- [ ] Docker replay CTA from real receipt refs

---

## 22. Glossary

| Term | Meaning |
|------|---------|
| **Lane** | One exploit agent row on the race timeline |
| **Track %** | Horizontal position 0–100 on lane track (mockup T/30 × 100) |
| **Band** | Vertical zone in lane: top, mid-above, center, bottom |
| **Terminal** | Lane end state: killed, blocked, promoted, fastest_crash |
| **Lineage** | Parent→child spawn fork (green SVG branch) |
| **Playhead** | Vertical cyan cursor at current replay time |
| **Design view** | `#battle` mockup-faithful shell over `mockupDesignLanes` |
| **Receipt view** | shadcn/Tailwind shell over `receiptBackedFixture` |
| **MOCK_SPECS** | Authoritative 11-lane fixture in `battle-mockup-lanes.ts` |

---

## 23. Related documents

| Document | Path |
|----------|------|
| HTML mockup (visual authority) | `agent-skills/skills/battle/mockups/battle-004-shell-preserving-scroll-timeline.html` |
| Reference PNG | `packages/ux-lab/assets/battle-mockup/reference.png` |
| Backend boundary | `agent-skills/skills/battle/docs/BATTLE_004_DESIGN_HANDOFF.md` |
| Orchestration model | `agent-skills/skills/battle/docs/PROJECT_KNOWLEDGE.md` |
| GOAL / visual references | `agent-skills/skills/battle/GOAL.md` |
| Element reference crops | `packages/ux-lab/assets/battle-mockup/elements/` |
| Interaction testing skill | `.cursor/skills/test-interactions/SKILL.md` |
| React qid conventions | `.pi/skills/best-practices-react/SKILL.md` |

---



---

## 24. Agent implementation workflow

This section mirrors the **test-interactions** skill: deterministic spec → implementation → live verification → optional visual review. A project agent must follow this order; do not invent layout from screenshots alone.

### Architecture: Spec → Build → Verify → Review

```
SPEC stage (this file + HTML mockup + reference PNG)
├── Authority hierarchy (top of DESIGN.md)
├── Element catalog (§26) — DOM, CSS, image, animation per element
├── Animation registry (§27) — transitions and keyframes
└── data-qid / interaction manifest (§28)

BUILD stage (React + battle-mockup-elements.css)
├── Match HTML class names under .battle-mockup-shell
├── Wire fixture data from lib/mockup-design-fixture.ts + battle-mockup-lanes.ts
├── Use D3 scale for time→pixels (never full-canvas width in design view)
└── Add missing data-qid + data-qs-action + title on interactive nodes

VERIFY stage (deterministic — no LLM)
├── ./scripts/verify-battle-ui.sh          → 17/17 + 48/48 + 13/13 DOM
├── python3 scripts/compare-battle-mockup.py → pixel regression guard
├── test-interactions run (§28 manifest)     → CDP click/hover + assertions
└── compare captures vs §25 E-crops + compare-battle-mockup regions

REVIEW stage (optional, batched LLM)
└── /review-design with persona on §25 reference crops + live captures
    Visual critique does NOT change pass/fail verdicts.

ON FAILURE (test-interactions or structural gates)
├── Read failure evidence: results.json + INTERACTION_REPORT.md + screenshots
├── Classify: implementation drift vs spec gap vs manifest bug
├── Fix implementation to match DESIGN.md + HTML mockup (usual case)
├── If mockup/HTML authority changed: update DESIGN.md §5/§6/§26 first, then code
├── If assertion was wrong: fix battle-design-interactions.json (assertions are [data-qid] only for clicks)
├── Re-run full VERIFY stack until mocked: no · live: yes
└── Record outcome in §29 changelog (version bump when spec or manifest changes)
```

### Per-element implementation checklist

When implementing or polishing any element, complete **all** rows:

| Step | Action | Pass criterion |
|------|--------|----------------|
| 1 | Read HTML mockup block for the class | Class name matches exactly |
| 2 | Open §26 reference image | Visual intent understood |
| 3 | Implement in listed React component | Design branch only (`isBattleDesignView()`) |
| 4 | Add CSS in `battle-mockup-elements.css` | Rule scoped `.battle-mockup-shell .{class}` |
| 5 | Copy fixture strings from §5 / §8 | No invented labels or scores |
| 6 | Wire states from §6 | hover / selected / collapsed behave like HTML |
| 7 | Apply motion from §27 | duration/easing match HTML |
| 8 | Add `data-qid` if interactive | 4-attribute rule (§28) |
| 9 | Run live verification | `mocked: no · live: yes` |

### Critical rules (same spirit as test-interactions)

1. **HTML class names are the contract** — not Tailwind equivalents in design view.
2. **Reference PNG is visual truth** — `assets/battle-mockup/reference.png` and §25 crops.
3. **Fixture data is copy truth** — scores, event text, lane names from `MOCK_SPECS`.
4. **Deterministic tests decide pass/fail** — pixel `mean_diff` is regression-only.
5. **Every interactive control needs `data-qid`** — 28/28 coverage; full CDP inventory in §28.

---

## 25. Visual reference index

Stable crops from the HTML-derived reference PNG. Paths relative to `packages/ux-lab/`.

| ID | Image | Region | Size (approx) | Primary classes |
|----|-------|--------|---------------|-----------------|
| `E00` | `assets/battle-mockup/elements/00-full-shell.png` | Entire viewport | 1672×941 | `.battle-mockup-app` |
| `E01` | `assets/battle-mockup/elements/01-header.png` | Header row | 1672×168 | `.topbar` |
| `E02` | `assets/battle-mockup/elements/02-score-block.png` | VS score | 630×128 | `.score`, `.scoreSide` |
| `E03` | `assets/battle-mockup/elements/03-live-events.png` | Live ticker | 510×128 | `.liveEvents`, `.liveEventRow` |
| `E04` | `assets/battle-mockup/elements/04-left-rail.png` | Left rail | 260×692 | `.leftRail`, `.railBlock` |
| `E05` | `assets/battle-mockup/elements/05-blue-strip.png` | Blue interventions | 1052×72 | `.blueStripCenter`, `.bluePatch` |
| `E06` | `assets/battle-mockup/elements/06-graph-titlebar.png` | Graph toolbar | 1052×36 | `.graphTitleBar`, `.zoomBtn` |
| `E07` | `assets/battle-mockup/elements/07-timeline-overview.png` | Minimap | 1052×36 | `.timelineOverview`, `.overviewMark` |
| `E08` | `assets/battle-mockup/elements/08-timeline-axis.png` | TIME + stages | 1052×72 | `.axis`, `.stage` |
| `E09` | `assets/battle-mockup/elements/09-timeline-lanes.png` | Lane matrix | 1052×548 | `.rows`, `.row` |
| `E10` | `assets/battle-mockup/elements/10-lane-row-selected.png` | Selected lane | 1052×92 | `.row.selected`, `.markerIcon` |
| `E11` | `assets/battle-mockup/elements/11-agent-detail.png` | Agent pane | 360×692 | `.right`, `.field` |
| `E12` | `assets/battle-mockup/elements/12-legend.png` | Legend strip | 1672×34 | `.footerLegend` |
| `E13` | `assets/battle-mockup/elements/13-footer.png` | Footer controls | 1672×47 | `.footer`, `.footChip` |

**Full reference:** `assets/battle-mockup/reference.png`  
**Live diff crops:** `.artifacts/battle-mockup-compare/regions/{timestamp}/` (current vs reference vs diff per region)

### How to use reference images

1. **Before coding** — open the crop for the region you are touching; match spacing, color weight, and typography scale.
2. **After coding** — run `compare-battle-mockup.py`; open `{region}-diff.png` to see RGB drift hotspots.
3. **For VLM review** — stitch §25 crops with live captures (test-interactions `vlm_image` preprocessing) and run `/review-design --persona margaret-chen`.

---

## 26. Element catalog

Each entry: **Ref** (§25 image), **Component**, **HTML classes**, **Dimensions**, **States**, **Motion** (§27), **Fixture**, **data-qid** (if interactive).

### 26.1 Shell & chrome

#### E00 — App shell

| Field | Value |
|-------|-------|
| **Ref** | E00 |
| **Component** | `BattleSpectatorArena.tsx` |
| **Classes** | `.battle-mockup-app` → `.battle-mockup-shell` |
| **Layout** | max-width 1672px; grid rows: topbar auto · main 1fr · legend 34px · footer 64px |
| **Background** | radial gradient `#0a1628` → `#040a12`; padding 16px |
| **Motion** | none |
| **data-qid** | — |

#### E12 — Legend

| Field | Value |
|-------|-------|
| **Ref** | E12 |
| **Component** | `BattleSpectatorArena` (inline `BattleMockupLegend`) |
| **Classes** | `.footerLegend` |
| **Content** | 7 items: Exploit Progress (red), Blue Intervention, Blocked, Killed, Useful Signal, Promoted/Survivor, Fastest Crash |
| **Icons** | Lucide via `Icons.*` at 14px |
| **Motion** | none |
| **data-qid** | — (display-only) |

---

### 26.2 Header (`.topbar`)

#### E01 — Header block

| Field | Value |
|-------|-------|
| **Ref** | E01 |
| **Component** | `BattleHeader.tsx` |
| **Classes** | `.topbar` > `.headerBlock` > `.title` / `.metaInline` |
| **Grid** | `minmax(340px,1fr) 250px minmax(360px,1fr)`; min-height 118px |
| **Title copy** | `BATTLE-004 · POST /api/import-zip` |
| **Subtitle** | `CWE-22 Zip Slip` with `.dim` pipe separators |
| **Meta** | Arena `ZIP_SLIP_LAB`, Objective, Target, Difficulty `HIGH`, Round `10:14 / 20:00` |
| **Motion** | `.topbar::before` 1px gradient hairline (static) |
| **data-qid** | receipt events only: `battle:events:item:{id}` |

#### E02 — Score block

| Field | Value |
|-------|-------|
| **Ref** | E02 |
| **Component** | `BattleHeader.tsx` |
| **Classes** | `.score.battle-score-block` > `.scoreSide.red|blue` > `.scoreNum` |
| **Values** | Red **8.4** (Bug icon left); Blue **7.2** (Shield icon right); `.vs` center |
| **Visual** | Octagonal clip-path inner border via `.score::before` |
| **Typography** | `.scoreNum` 26px/800; `.scoreLabel` uppercase 10px |
| **Motion** | none |
| **data-qid** | — |

#### E03 — Live events ticker

| Field | Value |
|-------|-------|
| **Ref** | E03 |
| **Component** | `BattleHeader.tsx` |
| **Classes** | `.liveEvents` > `.liveEventsHead` + `.liveEventRow` × 3 |
| **Head** | `.dot.red` pulsing + `LIVE EVENTS` |
| **Rows** | See §5.1 table (10:14:32 / 10:14:18 / 10:13:55) |
| **Row anatomy** | `.leTime` (mono) · `.leIcon.{green|blue}` · `.leText` with `b.green|b.blue` highlight |
| **Motion** | `.dot` → `pulse-dot` 2.5s infinite (§27) |
| **States** | `:hover` row `background: rgba(255,255,255,.03)` |
| **data-qid** | `battle:events:item:{id}` (receipt); design rows are static buttons |

---

### 26.3 Left rail (`.leftRail`)

#### E04 — Race leaders

| Field | Value |
|-------|-------|
| **Ref** | E04 (top third) |
| **Component** | `SpectatorRail.tsx` |
| **Classes** | `.railBlock` > `.railHead` + `.leaderItem` |
| **Rows** | 3 leaders — see §5.2 table |
| **Anatomy** | `.rank.r1|r2|r3` · `.liName` · `.liGen` · `.liRight` (icon + time) |
| **States** | `.leaderItem:hover`, `.leaderItem.selected` → green tint `rgba(60,240,122,.08)` |
| **Motion** | background transition 0.15s |
| **data-qid** | `battle:leaderboard:item:{laneId}` |
| **data-qs-action** | `BATTLE_LEADERBOARD_SELECT` |
| **title** | `Select {name} on race timeline` |

#### E04b — Team standings

| Field | Value |
|-------|-------|
| **Ref** | E04 (middle) |
| **Classes** | `.standRow.red` / `.standRow.blue` |
| **Content** | Red 8.4 / Blue 7.2 with `.standIcon`, `.standName`, `.standScore` |
| **Motion** | none |

#### E04c — Agent status grid

| Field | Value |
|-------|-------|
| **Ref** | E04 (bottom) |
| **Classes** | `.statusRow` × 6 |
| **Fixture** | `mockupAgentStatus()` — Running, Queued, Killed, Blocked, Promoted, Crashed counts |
| **Motion** | none |

---

### 26.4 Center timeline

#### E05 — Blue control strip

| Field | Value |
|-------|-------|
| **Ref** | E05 |
| **Component** | `BlueControlStrip.tsx` |
| **Classes** | `.blueStripCenter.battle-blue-strip` |
| **Layout** | 2-col grid `290px | 1fr`; label left, `.bluePatchRow` right |
| **Stats** | `Interventions 4` · `Blocks 2` in `.blueStat` |
| **Patches** | 3 × `.bluePatch` at track % 18, 42, 68 — CanonGuard v1, PathSanity Patch, Boundary Shield |
| **Patch anatomy** | Shield 14px · label · `.bpSub` timestamp |
| **Background** | `linear-gradient(90deg, rgba(8,24,48,.85), rgba(4,12,24,.75))` |
| **Motion** | none on patches |
| **data-qid** | — (patches are display-only in design) |

#### E06 — Graph title bar

| Field | Value |
|-------|-------|
| **Ref** | E06 |
| **Component** | `RaceViewport.tsx` |
| **Classes** | `.graphTitleBar` |
| **Height** | 36px |
| **Content** | `Evolution & Progress Graph` · `.zoomHint` · `.zoomBtns` / `.zoomBtn` − + · `.playheadLabel` |
| **Playhead label** | `PLAYHEAD 10:14:32` with cyan bar `::before` |
| **States** | `.zoomBtn:hover` border brighten |
| **Motion** | zoom button border `transition` 0.15s (HTML) |
| **data-qid** | `battle:timeline:zoom:out`, `battle:timeline:zoom:in` |

#### E07 — Timeline overview (minimap)

| Field | Value |
|-------|-------|
| **Ref** | E07 |
| **Component** | `TimelineOverview.tsx` |
| **Classes** | `.timelineOverview` > `.overviewSpacer` (290px) + `.overviewTrackWrap` + `.scrollHint` |
| **Marks** | `.overviewMark.crash` @ 77%, `.overviewMark.promoted` @ 88% |
| **Viewport** | `.overviewViewport` synced to `graphWrap` scrollLeft/width |
| **Motion** | `.scrollHint.hidden` opacity 0 over 0.2s when scrolled to end |
| **data-qid** | — |

#### E08 — Timeline axis

| Field | Value |
|-------|-------|
| **Ref** | E08 |
| **Component** | `BattleTimelineAxis.tsx` |
| **Classes** | `.axis` > `.axisCorner` (`TIME`) + `.axisTrack` > `.ticks` + `.stage` |
| **Ticks** | 10:04 … 10:14 at x% 0,20,40,60,80,100 |
| **Stage** | 5 equal columns 34px — Research, Payload, Mutate, Retry, Terminal + Lucide 12px |
| **Sticky** | `.axis` sticky top within scroll |
| **Motion** | none |
| **data-qid** | — |

#### E09 — Lane row matrix

| Field | Value |
|-------|-------|
| **Ref** | E09, E10 |
| **Component** | `LaneRow.tsx`, `LaneEventMarker.tsx`, `LaneEventLabel.tsx` |
| **Classes** | `.rows` > `.row.{root|child}.{selected?}.{childIndent?}` |
| **Heights** | root 92px (`--row-h-root`); child 86px (`--row-h-child`) |
| **Bands** | `.laneTop` phases · `.laneMidAbove` tokens · `.laneCenter` line+markers · `.laneBottom` terminals |
| **Line** | `.line.red|green|purple` span from `xStart`–`xEnd` |
| **States** | `.row:hover`, `.row.lineageHot` → `rgba(90,173,255,.03)`; `.row.selected` green gradient + inset bar |
| **Motion** | row `background 0.15s` |
| **data-qid** | `battle:lane:{id}`, `battle:track:{id}`, `battle:marker:{laneId}:{kind}` |

#### E09a — Center marker icons (`.markerIcon`)

| Field | Value |
|-------|-------|
| **Ref** | E10 (track center band) |
| **Classes** | `.markerIcon.tok{Yellow|Blue|Red|Green|Purple}[.terminal][.big]` |
| **Kinds** | See §9 marker taxonomy |
| **Size** | default 22px circle; `.big` 26px for terminal rockets |
| **Motion** | **none in design** (HTML static; no framer-motion pulse) |
| **data-qid** | `battle:marker:{laneId}:{kind}` |
| **data-battle-marker-icon** | required for DOM count ≥16 |

#### E09b — Playhead

| Field | Value |
|-------|-------|
| **Ref** | E09 (cyan vertical line) |
| **Component** | `BattlePlayheadCursor.tsx` in `.playheadOverlay` |
| **Classes** | `.playhead.battle-playhead` |
| **Position** | T=23.1 → 10:14:32 |
| **Visual** | 2px cyan gradient + glowing dot `::before` |
| **Motion** | receipt mode: animated with `playing`; design: static at fixture position |
| **data-qid** | isolation harness uses `.battle-playhead` |

#### E09c — Lineage branches

| Field | Value |
|-------|-------|
| **Ref** | E09 (green SVG curves) |
| **Component** | `BattleLineageFlow.tsx` |
| **Classes** | `.battle-lineage-svg` > `path.battle-lineage-branch` |
| **Stroke** | `rgba(60,240,122,.55)` width 2; drop-shadow |
| **Count** | 5 branches (857→A, 912→A/B/C/D) |
| **Motion** | none |
| **data-qid** | — |

#### E09d — Scroll chrome

| Field | Value |
|-------|-------|
| **Ref** | E09 (right edge gradient) |
| **Classes** | `.graphWrapHost` > `.graphWrap` + `.graphScrollHint` |
| **Hint copy** | `More outcomes →` |
| **Motion** | `.graphScrollHint.hidden` opacity 0 / 0.2s when at scroll end |
| **data-qid** | `battle:timeline:scroll` on `.graphWrap` |

---

### 26.5 Agent detail (`.right`)

#### E11 — Agent detail pane

| Field | Value |
|-------|-------|
| **Ref** | E11 |
| **Component** | `MockupAgentDetailPane.tsx` |
| **Classes** | `.right.battle-mockup-agent-pane` |
| **Default lane** | `payload-857-A` — Replay Fork |
| **Hero** | `.agentBug` + `.agentName` 26px + `.agentPayload` mono |
| **Badge** | `.statusPill` FASTEST CRASH (when terminal) |
| **Docker CTA** | `.dockerReplay.dockerReplayTop` — `RUN REPLAY IN DOCKER` |
| **Fields** | Status · Current Loop (`.loopGrid` 3-col) · Inherited · Mutation · Latest Receipt |
| **Receipt block** | `.receiptBlock` monospace pre-wrap |
| **States** | `.dockerReplay:hover` border/background brighten |
| **Motion** | docker replay hover 0.15s |
| **data-qid** | `battle:agent-pane:{lane.id}` |

---

### 26.6 Footer (`.footer`)

#### E13 — Footer controls

| Field | Value |
|-------|-------|
| **Ref** | E13 |
| **Component** | `BattleMockupFooter.tsx` |
| **Classes** | `.footer` > `.liveBadge` + `.footerControls` + `.fit` |
| **Groups** | SPEED 1x/2x/4x/8x · FOCUS All/Red/Blue · VIEW ☰▥▦ |
| **Chip class** | `.footChip` — active green border `rgba(60,240,122,.35)` |
| **Play toggle** | `.fit` — pause/play playhead |
| **Motion** | none defined (instant state swap) |
| **data-qid** | `battle:footer:speed:*`, `battle:footer:focus:*`, `battle:footer:playhead`, `battle:footer:spectator-arm` |

---

## 27. Animation & motion registry

**Pixi effect mapping** (spike path): semantic events → procedural effects (`research` jog, `blocked` shield, `killed` burst, `fastest_crash` rocket, etc.). Receipt-backed only — see `BATTLE_RACE_ENGINE.md` and `best-practices-battle-pixi`. Deterministic mode: `BattleEngineRenderTestMode`.


Design view uses **CSS only** unless noted. Receipt mode may add framer-motion on lane rows — do not port to design markers.

| ID | Element | Property | Value | Trigger | HTML line |
|----|---------|----------|-------|---------|-----------|
| A01 | `.dot` (live events head) | `animation` | `pulse-dot 2.5s ease-in-out infinite` | always | mockup L47 |
| A02 | `.dot` | `@keyframes pulse-dot` | opacity 1 → 0.55 → 1 | — | mockup L50 |
| A03 | `.leaderItem` | `transition` | `background 0.15s` | hover/selected | mockup L100 |
| A04 | `.row` | `transition` | `background 0.15s` | hover/selected/lineageHot | mockup L177 |
| A05 | `.zoomBtn` | `transition` | `border-color` on hover | hover | mockup L137 |
| A06 | `.scrollHint` | `transition` | `opacity 0.2s` | scroll end | mockup L151 |
| A07 | `.graphScrollHint` | `transition` | `opacity 0.2s` | scroll end | mockup L154 |
| A08 | `.dockerReplay` | `transition` | border/background on hover | hover | mockup L249 |
| A09 | `.liveEventRow` | `transition` | `background` on hover | hover | receipt header |
| A10 | Playhead | JS-driven | scroll + optional tick | `playing=true` | receipt footer |

### Motion anti-patterns

| Do not | Do instead |
|--------|------------|
| framer-motion on `.markerIcon` in design | static icons per HTML |
| CSS pulse on lane lines | only `.dot` pulses in header |
| Animate lineage paths | static SVG |
| Invent easing curves | copy HTML durations (0.15s UI, 0.2s hint fade, 2.5s dot pulse) |

### Scroll-sync behavior (not CSS animation)

| Source | Target | Rule |
|--------|--------|------|
| `graphWrap.scrollLeft` | `.overviewViewport` left/width | proportional to scrollWidth |
| `graphWrap` at end | `.graphScrollHint`, `.scrollHint` | add `.hidden` |
| Ctrl+wheel on timeline | `zoom` state | `stepTimelineZoom` in `timeline-playback.ts` |
| Zoom change | `.graph` minWidth | `timelineContentWidth(zoom)` |

---

## 28. Interaction testing (`test-interactions`)

Deterministic UI testing for `#battle` follows the **test-interactions** skill. Read `.pi/skills/best-practices-react/SKILL.md` first (4-attribute rule).

### Prerequisites

```bash
# Dev server (live DOM required)
cd packages/ux-lab
UX_LAB_UI_PORT=3012 npm run dev

# Structural gates (run before interaction tests)
./scripts/verify-battle-ui.sh
python3 scripts/compare-battle-mockup.py
python3 scripts/verify-data-qid.py src/components/battle/dual-agent/
```

### Manifest location

`packages/ux-lab/src/components/battle/dual-agent/battle-design-interactions.json`

Authoritative manifest — **do not** duplicate a stale excerpt here. Edit the JSON file directly when adding interactions.

| Field | Value |
|-------|-------|
| Surfaces | 1 (`battle-design`) |
| Element groups | 9 |
| Interactions | 57 |
| Interactive `[data-qid]` targets | 50 (full live DOM inventory) |
| `qid_compliance` scan | `false` — mockup HTML uses compact 30px `footChip` and 20px `.chev`; per-click `assert_title` / `assert_qs_action` still run |

### Element groups (manifest)

| Group | Coverage |
|-------|----------|
| `shell-mockup-fidelity` | 11 lanes, ≥16 markers, `.center` / `.topbar`, fixture copy (`8.4`, `ZIP_SLIP_LAB`, `FASTEST CRASH`) |
| `leaderboard-all` | 3 race leaders → agent pane |
| `lanes-all` | 11 lane rows → agent pane |
| `markers-all` | 16 timeline markers → lane selection |
| `lane-collapse` | `payload-857` / `payload-912` collapse (10↔11 rows) |
| `timeline-zoom` | zoom in/out, scroll shell, `.graphWrapHost` |
| `footer-controls` | 4 speeds, 3 focus chips, playhead, spectator arm |
| `live-events` | 3 header live-event rows |
| `agent-pane-chrome` | docker replay CTA, close control |

### Run

```bash
# From test-interactions skill directory
./run.sh run \
  --manifest /path/to/battle-design-interactions.json \
  --output-dir ./captures/battle/

# Optional visual review (persona required; does not change pass/fail)
./run.sh review --captures ./captures/battle/ --persona margaret-chen
```

### Latest live result (2026-07-06)

| Gate | Result |
|------|--------|
| test-interactions | **57 PASS / 0 FAIL** |
| verify-battle-ui.sh | 17/17 + 48/48 + 13/13 DOM |
| compare-battle-mockup.py | mean_diff 9.29 (threshold 26.5) |
| verify-data-qid.py | 28/28 (100%) |

`mocked: no · live: yes` on `http://127.0.0.1:3012/#battle`

### Visual screenshot verification (required)

DOM/assertion PASS is **not** sufficient. After `test-interactions run`, compare **actual step screenshots** against **expected mockup evidence**:

| Evidence type | Source | Use |
|---------------|--------|-----|
| Full shell | `E00` + `reference.png` | Default shell screenshot (`shell-mockup-fidelity`) |
| Per-region | §25 `E01`–`E13` crops | Crop live capture at §26 boxes; pixel `mean_diff` |
| Region diff artifacts | `compare-battle-mockup.py` | `{region}-current.png` vs `{region}-reference.png` vs `{region}-diff.png` |
| State-specific captures | test-interactions `captures/battle-design/*.png` | After lane/leader/marker clicks — agent pane must match `E11` intent |

```bash
# 1) Live region regression (default #battle state)
python3 scripts/compare-battle-mockup.py

# 2) Element crops from interaction shell screenshot
python3 scripts/compare-battle-element-captures.py \
  --capture /path/to/captures/battle-design/0001_shell-mockup-fidelity_screenshot.png

# 3) Optional VLM critique (does not change pass/fail)
./run.sh review --captures ./captures/battle/ --persona margaret-chen
```

**Pass criteria:** each compared element `mean_diff` ≤ 26.5 (same threshold as `compare-battle-mockup.py`). On visual FAIL: treat like interaction FAIL — fix implementation or update DESIGN.md §25/§26 boxes if mockup authority changed, then re-capture.

**Latest element compare (2026-07-06):** shell capture vs `E00`/`E01`/`E04`/`E11`/`E13` — all pass (overall 12.7, worst element E01 15.54). Artifacts: `.artifacts/battle-element-compare/`.

### When an interaction fails — update docs

The manifest encodes **expected behavior from this spec**. On any FAIL:

1. **Read evidence** — `results.json`, `INTERACTION_REPORT.md`, step screenshot under `captures/battle-design/`.
2. **Classify the failure**
   - **Implementation drift** — DOM/class/copy/state wrong vs §4–§8, §26. Fix React/CSS; do not weaken the assertion.
   - **Spec gap** — HTML mockup or fixture truth changed but DESIGN.md lags. Update §5/§6/§26 (and §27 if motion), then implementation.
   - **Manifest bug** — wrong selector, wrong expected agent pane, or `assert_count` bounds off (e.g. collapse row counts). Fix `battle-design-interactions.json` only.
3. **Never use non-`[data-qid]` selectors for click targets.** Structural checks (`.center`, `[data-lane-row]`) are allowed on screenshot steps only.
4. **Re-run the full VERIFY stack** (verify-battle-ui, compare-battle-mockup, test-interactions run).
5. **Changelog** — add a §29 row when the spec or manifest changes; bump version in the header.

Known functional gap (not a structural/mockup failure): `battle:agent-pane:close` has qid/title but no `onClick` yet — pane stays open after click.

### Deterministic assertions mapped to DESIGN.md

| Assertion | DESIGN source | Example |
|-----------|---------------|---------|
| `assert_selector` | §26 DOM tree | agent pane after leader click |
| `assert_count` | §16 DOM checklist | `[data-lane-row]` == 11 |
| `assert_text` / `assert_texts` | §5 fixture copy | score `8.4`, agent pane `FASTEST CRASH` |
| `assert_visible` | §4 shell tree | `.graphWrapHost`, `.topbar` |
| `assert_min_size` | COTS C02 | close button ≥44×44 (where mockup allows) |
| `assert_qs_action` / `assert_title` | §14 | every interactive click |

### QID registry (design `#battle`)

All interactive design-view controls implement the **4-attribute rule** (`data-qid`, `data-qs-action`, `title`, `useRegisterAction`):

```bash
python3 scripts/verify-data-qid.py src/components/battle/dual-agent/
# Expected: 100% coverage (28/28 interactive elements)
```

| Surface | Key data-qid prefixes |
|---------|----------------------|
| Timeline zoom | `battle:timeline:zoom:out`, `battle:timeline:zoom:in` |
| Timeline scroll | `battle:timeline:scroll` |
| Footer | `battle:footer:speed:*`, `battle:footer:focus:*`, `battle:footer:playhead`, `battle:footer:spectator-arm` |
| Lanes | `battle:lane:*`, `battle:lane:collapse:*` |
| Markers | `battle:marker:{laneId}:{kind}` |
| Live events | `battle:events:item:{id}` |
| Agent pane | `battle:agent-pane:{id}`, `battle:agent-pane:close`, `battle:agent-pane:docker-replay:{id}` |
| Leaderboard | `battle:leaderboard:item:{laneId}` |


## 30. Backend / UX contract

Live backend integration follows **`BACKEND_UX_CONTRACT.md`** (also `agent-skills/skills/battle/docs/BATTLE_004_BACKEND_UX_CONTRACT.md`).

### Authority split

| Layer | Owns |
|-------|------|
| **Backend** | Global `battle.clock.v1`, `at_seconds`, canonical `events[]`, Judge terminal truth, lineage/spawn receipts, `render_guards`, snapshot + SSE/JSONL |
| **UI** | Pixel x from D3 scale, zoom, `scrollLeft`, follow thresholds, easing/CSS animation, layout constants |

### Playback modes → UI behavior

| `clock.mode` | Playhead | Data |
|--------------|----------|------|
| `live` | `current_seconds` from server | Stream + snapshot |
| `receipt_replay` | Receipt timestamps | Generated fixture |
| `design_fixture` | `mockup-design-fixture.ts` | `#battle` parity only — **not** production truth |

### Types (`lib/battle-types.ts`)

- `BattleClockV1`, `BattleTimelineControlV1` — preferred for new adapters
- `BattleSemanticEventV1`, `BattleLiveEventEnvelopeV1`, `BattleSnapshotV1`
- `BattleTimeline.playhead.current_x` — **deprecated** for backend; UI derives x locally

### UI implementation notes

- Default scroll follow: `scroll_after_threshold` (`timeline-playback.ts`)
- Interpolation: receipt segments (`BattleReceiptSegmentV1`) or live `active_segment` only
- Child lanes: appear at spawn `at_seconds`; design view may use `mockupDesignLanes` without receipts
- Round duration: from `round_config` / fixture — never hardcoded in React

When backend contract changes, update `BACKEND_UX_CONTRACT.md` first, then types, then adapter.



## 32. Race engine (Pixi)

**Phase 1 authority:** `BATTLE_RACE_ENGINE_PIXI_SPIKE.md` — not default until acceptance gates pass.


Center race viewport animation follows **`BATTLE_RACE_ENGINE.md`**.

### Architecture

```text
React DOM shell (sticky labels, axis, blue strip, qids)
└── Pixi track world (#battle?engine=pixi spike)
    ├── procedural runners / effects
    ├── playhead inside track plane
    └── DOM hit-target mirrors (qid + a11y)
```

### Rollout

| Phase | Gate |
|-------|------|
| 1 | `?engine=pixi` spike; DOM `RaceViewport` default |
| 2 | Design + receipt sparse fixture; deterministic screenshot frame |
| 3 | Replace timeline body when parity + mirrors pass |
| 4 | Pixi default |

### Authority (unchanged)

Normalized `battle.normalized_ux_fixture.v1` only. `events[]` canonical; terminal effects require receipts.




## 33. Engine migration (optional renderer)

This section documents the **optional Pixi race engine** — an engine migration, not a rewrite of the BATTLE-004 design spec.

| Phase | Behavior |
|-------|----------|
| 1 (now) | `BattleRacePixiSpike` behind `#battle?engine=pixi`; DOM default |
| 2 | Design + receipt sparse fixture; deterministic paused-frame compare |
| 3 | Replace timeline body when parity + qid/a11y pass |
| 4 | Pixi becomes default center renderer |

**Agent read order for Pixi work:**

1. `pixijs` router skill → specialized `pixijs-*` skill
2. `$best-practices-battle-pixi` overlay
3. `BATTLE_RACE_ENGINE.md` + `BACKEND_UX_CONTRACT.md`

**Non-negotiables:** one normalized fixture; renderer-neutral backend; DOM mirrors for qids; fail-closed receipt effects; 290px gutter.


## 31. Changelog

| Date | Version | Change |
|------|---------|--------|
| 2026-07-05 | 1.0 | Initial authoritative spec: region DOM trees, fixture catalog, marker taxonomy, coordinate system, class registry, verification, migration path |
| 2026-07-05 | 1.1 | Comprehensive pass: TOC, state/interactions, data contracts, per-lane events, center shell tree, overview/stage HTML authority, icon mapping, data-qid registry, pixel baselines, implementation delta table, glossary, isolation harness index |
| 2026-07-06 | 2.0 | Agent workflow (§24), visual reference crops (§25), per-element catalog with images (§26), animation registry (§27), test-interactions manifest + qid gap table (§28) |
| 2026-07-06 | 2.1 | Close all design-view QID gaps: footer, zoom, lane collapse, live events, agent pane; 100% verify-data-qid coverage; touch targets min-h-11 |
| 2026-07-06 | 2.2 | Full test-interactions manifest (57 steps, 50 qids); failure→doc workflow; live 57/57 PASS documented |
| 2026-07-06 | 2.3 | §28 visual screenshot verification: interaction captures vs E-crops + compare-battle-element-captures.py |
| 2026-07-06 | 2.4 | `BACKEND_UX_CONTRACT.md` — clock, playback, scroll, animation authority, live transport; TypeScript v1 types |
| 2026-07-06 | 2.7 | `BATTLE_RACE_ENGINE_PIXI_SPIKE.md` — Phase 1 Pixi spike companion contract |
| 2026-07-06 | 2.6 | Engine migration docs: hybrid DOM/Pixi renderer, optional `#battle?engine=pixi`, §33 migration path; synced with `BATTLE_004_INTERFACE_IMPLEMENTATION_SPEC.md` |
| 2026-07-06 | 2.5 | `BATTLE_RACE_ENGINE.md` — Pixi hybrid DOM/Pixi split, engine input contract, `?engine=pixi` spike
