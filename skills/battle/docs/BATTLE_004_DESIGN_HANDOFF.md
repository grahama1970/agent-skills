# BATTLE-004 Receipt Truth + UI Boundary Handoff

> **Former title:** BATTLE-004 Design Handoff (`BATTLE_004_DESIGN_HANDOFF.md` — filename kept for links)

**Timestamp**: 2026-07-06T12:42:20Z  
**Active Agent Role**: Battle internals implementer *or* mechanical UI implementer (see document map)  
**Status**: RECEIPT TRUTH HANDOFF (reviewers: if you see old title `# BATTLE-004 Design Handoff` only, refresh — this file was restructured) — mechanical UI spec is a separate document

## Document map

| Document | Path | Audience | Answers |
|----------|------|----------|---------|
| **This file** | `skills/battle/docs/BATTLE_004_DESIGN_HANDOFF.md` | Backend + all agents | What data may the UI truthfully show? What must not be faked? |
| **Interface spec** | `skills/battle/docs/BATTLE_004_INTERFACE_IMPLEMENTATION_SPEC.md` | Frontend project agents | How do I build the screen? Layout, components, CSS, animation, verification |
| **Authoritative UI spec (live)** | `pi-mono/packages/ux-lab/src/components/battle/dual-agent/DESIGN.md` | Frontend implementers | Full element catalog, reference crops, qid registry, stack locks |
| **HTML mockup** | `skills/battle/mockups/battle-004-shell-preserving-scroll-timeline.html` | Visual structure | Class names, copy, bands |
| **Reference PNG** | `pi-mono/packages/ux-lab/assets/battle-mockup/reference.png` | Pixel regression | Screenshot guard |
| **Backend/UX contract** | `skills/battle/docs/BATTLE_004_BACKEND_UX_CONTRACT.md` (+ ux-lab mirror) | Backend + frontend | Clock, events, renderer-neutral truth; no pixels |
| **Pixi Phase 1 spike** | `skills/battle/docs/BATTLE_RACE_ENGINE_PIXI_SPIKE.md` (+ ux-lab mirror) | Frontend Pixi agents | Optional `#battle?engine=pixi`; DOM default until gates pass |
| **Race engine overview** | `skills/battle/docs/BATTLE_004_RACE_ENGINE.md` | Frontend | Rollout phases, hybrid DOM/Pixi split |
| **Battle Pixi overlay skill** | `skills/best-practices-battle-pixi/SKILL.md` | Agents | Project Pixi constraints atop official `pixijs*` skills |


---

## Authority precedence

**When truth and visual density conflict, truth wins.**

| Question | Order |
|----------|-------|
| What may be claimed live? | Receipts → generated fixture → **this handoff** → interface spec → DESIGN.md |
| How to lay out the UI? | DESIGN.md → HTML mockup → reference PNG → interface spec → this handoff |

---

## Fixture modes

See `BATTLE_004_INTERFACE_IMPLEMENTATION_SPEC.md` §Fixture modes. Summary:

| Mode | Route gate | Lane source | Truth claims |
|------|------------|-------------|--------------|
| **Design parity** | `#battle` design view | `mockupDesignLanes` | Visual regression only — dense mockup state allowed |
| **Receipt-backed** | Receipt routes | `receiptBackedFixture` | Only mode for truthful Battle status |

```text
Never use mockupDesignLanes to justify live receipt claims.
Never pad receipt mode with mockup-only fastest crash, promotion, kills, or child lanes.
```

**Rule:** Do not treat this handoff as a freeform visual brief. It defines receipt truth and boundaries. For mechanical implementation, read the Interface spec and `DESIGN.md` first.

---

## 1. Purpose

This handoff prevents agents from turning BATTLE-004 into dashboard theater. The accepted Battle target is a dark acrylic/neon race interface with a scrollable DAW/movie-editor timeline.

It serves two audiences:

1. **Backend agents** — generate truthful Arena/Tau/Judge receipts for parent exploits that research, execute, retain useful signal, get blocked or handed off, and spawn child lanes.
2. **Frontend agents** — implement the accepted visual shell mechanically using the Interface spec; wire only receipt-backed or design-fixture data; never invent race outcomes.

### Non-negotiable warning

This document is **not** sufficient on its own to implement the interface. It defines the **receipt-backed data boundary** and what visual work is forbidden without external mockup authority.

Frontend agents **must** also read:

- `BATTLE_004_INTERFACE_IMPLEMENTATION_SPEC.md`
- `pi-mono/packages/ux-lab/src/components/battle/dual-agent/DESIGN.md`

Animations may reveal, highlight, or transition receipt-backed state. They **may not** imply unproven progress, kills, crashes, promotions, handoffs, or child lanes.

---

## 2. Visual target (summary)

Seven major regions (full layout in Interface spec):

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Header: title/meta          Scoreboard capsule              Live events      │
├──────────────────────────────────────────────────────────────────────────────┤
│ Blue Team control strip (patches aligned to timeline scale)                    │
├───────────────┬──────────────────────────────────────────────┬───────────────┤
│ Left rail     │ Scrollable timeline race view                │ Agent detail  │
│ leaders       │ lanes, markers, lineage, playhead, zoom     │ selected lane │
│ standings     │                                              │ replay CTA    │
│ status        │                                              │               │
├───────────────┴──────────────────────────────────────────────┴───────────────┤
│ Footer: spectator mode, speed, focus, playhead                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

Proportions, CSS tokens, component tree, and animation rules: **Interface spec + `DESIGN.md`**.

---

## 3. Component inventory (receipt vs UI state)

| Region | React components | Design parity source | Receipt-backed source | Invent data in receipt mode? |
|--------|------------------|----------------------|-------------------------|-------------------------------|
| Header | `BattleHeader` | `mockupLiveEvents`, config constants | `BattleEvent` stream | **No** |
| Score | `.score` | `mockupScoreboard()` | fixture team scores | **No** |
| Blue strip | `BlueControlStrip` | `mockupBlueStripStats()` | Blue/Judge receipts | **No** |
| Left rail | `SpectatorRail` | `mockupRaceLeaders()`, status fixture | normalized lane aggregates | **No** |
| Timeline | `RaceViewport`, `LaneRow`, lineage | `mockupDesignLanes` (dense mockup OK) | adapter `Lane[]` only | **No** |
| Agent detail | `MockupAgentDetailPane` | `mockupAgentDetail()` | lane + receipts | **No** |
| Footer | `BattleMockupFooter` | local UI state | local UI state | N/A (presentation only) |

Both modes preserve the same DOM class vocabulary. Design parity may show dense mockup races; receipt mode may not copy that density without proof.

---

## 4. Animation contract (summary)

Full registry: `DESIGN.md` §27.

| Animation | Trigger | Rule |
|-----------|---------|------|
| Live-events dot pulse | Always (header) | CSS `pulse-dot` 2.5s — decorative only |
| Row / leader hover | Hover / selected | Background transition 0.15s |
| Scroll hints | Timeline scroll end | Opacity fade 0.2s |
| Playhead | `playing` + battle clock | Reveals time; does not fabricate events |
| Marker pop | Receipt mode only | Design view: **static** markers (no framer-motion) |
| Lineage SVG | Parent spawn receipts | Drawn only when child lanes exist in fixture |
| Collapse children | User toggle | Height/visibility; no fake child rows |

```text
Animation is presentation only. It may reveal receipt-backed state.
It may not fabricate fastest crash, promotion, kill, handoff, or spawn.
```

---

## 5. Source of truth (visual references)

Visual references live in `skills/battle/GOAL.md` and `skills/battle/assets/`:

- `assets/battle-004-original-mockup.png`
- `assets/battle-004-original-mockup-reference.png`
- `assets/battle-004-core-mockup.png`
- `assets/battle-004-dense-timeline-reference-a.png`
- `assets/battle-004-dense-timeline-reference-b.png`
- `assets/battle-004-current-drift-timeline.png` (negative reference)

Canonical battle:

- Battle id: `battle-004`
- Target: `POST /api/import-zip`
- CWE: `CWE-22` — Zip Slip path traversal
- UX shape: original mockup shell, scrollable DAW timeline

Element reference crops: `pi-mono/packages/ux-lab/assets/battle-mockup/elements/`.

---

## 6. Design boundary (what local agents may / may not do)

The project agent must not originate non-trivial visual direction for this surface.

**Allowed local UI work:**

- Apply an accepted external mockup mechanically (`DESIGN.md` + HTML mockup).
- Fix deterministic layout defects: clipping, overlap, broken scroll, inaccessible controls, missing qid, build errors.
- Wire receipt-backed data into accepted components via adapter.
- Verify with `./scripts/verify-battle-ui.sh` and CDP screenshots.

**Forbidden local UI work:**

- Redesign header, score, Blue strip, rails, or Agent Detail from scratch.
- Add metric cards, dashboard rows, or fake density.
- Invent child lanes, fastest crash, promoted survivor, Blue kill, or live running state from sparse receipts.
- Keep tweaking visual style while backend lacks parent-spawn receipts.

When visual direction is needed, use the external design/WebGPT/Kimi loop with Battle visual references. Treat returned mockups as mechanical targets, not permission to invent data.

---

## 7. Current implemented reality

**Frontend (ux-lab `#battle` design shell):**

- Structural parity with HTML mockup: `.topbar`, `.leftRail`, `.center` scroll shell, `.right`, legend, footer.
- 11-lane design fixture, D3 `scaleLinear` timeline, SVG lineage, mockup CSS vocabulary.
- 100% `data-qid` coverage on interactive controls (`verify-data-qid.py`).
- Live verification: 17/17 capability, 48/48 isolation, 13/13 DOM checks (`verify-battle-ui.sh`).
- Authoritative spec: `DESIGN.md` v2.1+.

**Backend (receipt truth):**

- `arena_live_battle_proof.py` — parent-first Tau matrix, Judge replay, child Red spawn after parent `BLUE_SUCCESS`.
- `battle_event_adapter.py` — child lanes only when `lineage-receipts.json` proves parent/child.
- `local/battle-004-parent-spawn.normalized.json` — canonical local renderer fixture from live proof.
- Elapsed-axis model: use `timeline_elapsed_axis_model` for true elapsed-time placement; legacy `x` remains receipt-order percentages (`timeline_time_model.x_position_is_elapsed_time=false`).
- Do not show fastest crash, promoted survivor, Blue kill, or killed unless explicit receipts prove them.

---

## 8. Required backend internals next

1. Keep parent-spawn receipt rung live for canonical BATTLE-004 Arena/Tau flow.
2. Parent Red lanes: research → payload → useful signal → blocked/handoff (receipt-backed phases).
3. Child-spawn receipts: parent id, child id, spawn time, inherited context, Tau subagent receipt id, proof mode.
4. Materialize child lanes from handoff receipts only.
5. Judge only receipt-backed Red/Blue pairs.
6. Preserve per-step elapsed timestamps; regenerate elapsed-axis values when proofs change.
7. Emit fastest crash / promoted / kill only with explicit proof receipts.
8. Regenerate normalized UX fixture from receipts, not hand-authored UI data.

Parent-spawn invariant (do not draw branch first, backfill later):

```python
batch_id = await spawn_and_monitor_batch(
    annotations_file="annotations.json",
    pdf_path="document.pdf",
    poll_interval=2.0,
)
```

Battle equivalent: parent Tau/Arena event spawns child Tau workers with durable receipts.

---

## 9. Backend / UX contract

Full clock, playback, scroll, animation, and live-transport decisions: **`BATTLE_004_BACKEND_UX_CONTRACT.md`**.

Summary: backend owns semantic time/receipt truth; UI owns pixels and animation. One global battle clock. Judge owns terminal outcomes.

## 10. Adapter contract

`battle_event_adapter.py` fails closed — child lineage only with explicit receipts.

Minimum normalized `lane` fields:

```yaml
lane:
  id: string
  parentId: string | null
  children: string[]
  generation: number
  xStart: number
  xEnd: number
  runnerX: number
  runnerState: research | blocked_handoff | blocked | killed | promoted | fastest_crash
  events:
    - kind: research | payload | useful | handoff | spawn | retry | mutate | blocked | killed | promoted | fastest_crash
      x: number
      label: string
      receiptId: string
      proofMode: receipt_backed_fixture | live
  inheritedContext: string[]
  replay: object | null
```

Rules:

- Child `xStart` = spawn receipt position; `elapsed_line_must_start_at_x` from elapsed model — not global zero unless receipt says so.
- Parent-child connector originates at parent handoff/spawn event.
- `tau.spawned_child` requires parent and child receipts.
- `red.fastest_crash` / `red.promoted` / `blue.kill_confirmed` require explicit proof receipts.
- `blue.blocked_red` may derive from Judge `BLUE_SUCCESS`.

Frontend adapter must preserve event ID suffixes (`:top:`, `:icon:`, etc.) for band partition — see `DESIGN.md` §7–§9.

---

## 11. UI implementation boundary (after backend fix)

After parent-spawn receipts exist, React UI renders the generated fixture only:

- Original mockup shell proportions (`DESIGN.md` §4–§5).
- Scrollable, zoomable timeline (`.graphWrapHost` → `.graphWrap` → `.timelineShell`).
- Fixed lane-label gutter (`--label-w: 290px`); markers never under lane cards.
- Collapsible parent rows; children from fixture lineage only.
- Playhead tied to `battle_clock` / elapsed axis.
- Docker replay CTA only when `lane.replay` exists.
- Sparse proofs stay sparse.

---

## 12. Verification gates

**Backend:**

```bash
cd /home/graham/workspace/experiments/agent-skills/skills/battle
python -m py_compile src/battle_skill/arena_live_battle_proof.py src/battle_skill/battle_event_adapter.py src/battle_skill/cli.py
./run.sh arena-parent-spawn-proof battle-004 --red-workers 2 --blue-workers 2 --out <fresh-proof-dir>
```

Adapter checks: parent `children`, child `parentId`, `lineage.mode == receipt_backed`, no fake fastest/promotion/kill without receipts.

**Frontend (mechanical + live):**

```bash
cd /home/graham/workspace/experiments/pi-mono/packages/ux-lab
python3 scripts/verify-data-qid.py src/components/battle/dual-agent/
./scripts/verify-battle-ui.sh
python3 scripts/compare-battle-mockup.py
```

CDP screenshot review is mandatory for visual claims. DOM/text assertions alone are not visual proof.

Report format: `mocked: yes|no`, `live: yes|no`, what was exercised.

Use **split checklists** in `BATTLE_004_INTERFACE_IMPLEMENTATION_SPEC.md` §12:
- §12.1 Design fixture acceptance (mockup parity / `#battle` design mode)
- §12.2 Receipt-backed acceptance (truth gates)

---

## 12. Recommended next WebGPT request

Request backend internals, not another visual polish zip:

```text
battle-parent-spawn-lineage-backend-dropins.zip
```

Required: `arena_live_battle_proof.py`, `battle_event_adapter.py`, `cli.py`, `battle_live_handoff.py`, README, SHA256SUMS.

---

## 13. Human-facing status

- **Receipt truth handoff:** parent-spawn wiring in place; elapsed-axis model emitted; adapter fail-closed.
- **Interface implementation:** design `#battle` shell structurally complete per `DESIGN.md`; receipt-backed 11-lane matrix still gated on adapter.
- **Correct agent posture:** backend agents extend receipts; frontend agents follow Interface spec + `DESIGN.md`; verify live before claiming done.
