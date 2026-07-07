# Battle-004 Kimi Revision Request

## Status

The current standalone Kimi mockup is useful for timeline readability, but it is
not acceptable as the Battle-004 target because it changes the product shell.
Revise the standalone HTML/CSS/JS mockup before producing any React drop-ins.

Current reviewed mockup:

```text
/home/graham/Downloads/battle_004_modern_acrylic (1).html
/tmp/codex-clipboard-xtexjI.png
```

Authoritative goal:

```text
/home/graham/workspace/experiments/agent-skills/skills/battle/GOAL.md
```

## Source-Derived Step Model

1. **Battle shell**
   - Status: implemented in the accepted mockup, drifted in the Kimi mockup.
   - Required: restore the accepted Battle shell regions and proportions.
   - Missing in Kimi mockup: original left spectator rail, separate Blue Team
     Control Strip, original footer controls, top-right live event list, and
     metadata strip.

2. **Backend truth model**
   - Status: worker-matrix proof exists as a backend rung.
   - Required: production React may only render lanes, blocks, replay, kills,
     fastest crash, promotion, and children from receipt-backed data.
   - Mockup allowance: standalone HTML can illustrate the target dense state,
     but must mark fake/example density as visual-only.

3. **Race timeline**
   - Status: current Kimi mockup has a cleaner time ruler than the React route.
   - Required: combine that clarity with the original race graph shell.
   - Missing: global race time semantics and original shell preservation.

4. **Selected Agent / Agent Detail pane**
   - Status: partially aligned in Kimi mockup.
   - Required: keep `AGENT DETAIL` as the pane title, selected exploit as the
     primary object, Docker replay visible when backed by replay metadata.
   - Missing: original pane framing and compact hierarchy.

5. **Interaction proof**
   - Status: not accepted.
   - Required: revised HTML must visually pass at 1920x1080 and 1440x900 with
     no label/icon overlap and usable horizontal timeline scroll.

## Non-Negotiable Shell Requirements

Preserve these original Battle-004 regions:

- Header / campaign title.
- Red/Blue score block.
- Top-right live events list.
- Metadata strip: Arena, Objective, Target, Difficulty, Round Time.
- Blue Team Control Strip as a standalone horizontal band.
- Left spectator rail.
- Center race graph.
- Right `AGENT DETAIL` pane.
- Bottom controls/footer.
- Dark acrylic / neon red-blue-green visual style.

Do not replace the shell with a generic two-column timeline app.

## Layout Targets

At 1920x1080:

- Outer page padding: `16px`.
- Header including metadata: `150-170px`.
- Blue Team Control Strip: `64-76px`.
- Left spectator rail: `250-280px`.
- Right Agent Detail pane: `340-380px`.
- Footer controls: `56-68px`.
- Main graph uses all remaining space.
- Parent lane height: `72-86px`.
- Child lane height: `54-66px`.
- Event marker hit area: `34-44px`.
- Minimum graph content width: enough for 10-20 minutes of race time.

At 1440x900:

- Shell remains recognizable.
- Graph may scroll horizontally and vertically.
- Header, Blue strip, rail, right pane, and footer remain visible.
- No important text is clipped.

## Center Timeline Requirements

Use a DAW/NLE-style timeline model similar to Final Cut Pro or DaVinci Resolve:

- Sticky global time ruler.
- Horizontal pan/scroll.
- Zoom controls and visible zoom state.
- Sticky lane labels during horizontal scroll.
- Vertical scrolling for many lanes.
- Optional minimap/overview if helpful.
- Clear current-time/playhead marker.
- Label bands above/below each lane to prevent collisions.
- No event label may overlap another marker or label.
- No icon may overlap another icon.

Timeline semantics:

- Global race time starts at Battle start.
- Each exploit lane line starts at that exploit's spawn/materialization time.
- Root exploit lanes start at their materialization receipt time.
- Child lanes start at their parent handoff/spawn receipt time.
- Parent-child connectors originate from the parent event that emitted the
  child.
- The UI may show pre-spawn context in the right pane, but the lane line must
  not imply an exploit was running before it existed.

Required event information on lanes:

- Research.
- Payload/materialized.
- Mutate.
- Retry.
- Trigger.
- Observe.
- Useful signal.
- Blue patch/block.
- Dead end/killed only when proof exists.
- Promoted/fastest crash only when proof exists.
- Receipt markers.
- Timestamps on meaningful events.

## Right Pane Requirements

Keep the pane close to the accepted mockup:

```text
AGENT DETAIL
Selected exploit name
Generation / payload id
Status
Current loop
Inherited context
Mutation rationale
Latest receipt
Docker Replay
Recent events / streamed log
```

Rules:

- Spectator-facing primary label is the exploit name.
- Tau/subagent IDs are muted diagnostic metadata only.
- `REPLAY IN DOCKER` must be visible when replay metadata exists.
- If replay is receipt-only and not executable, label it as receipt replay, not
  live execution.
- Do not show hidden chain-of-thought.
- Do not query memory directly.
- Memory/project-knowledge appears only as emitted skill/tool events.

## Lucide Icon Map

Use Lucide icon names in the implementation plan and mockup comments. Avoid
emoji glyphs for production-facing controls.

| Concept | Lucide icon |
|---|---|
| Exploit runner | `Bug` or `Route` |
| Running / active exploit | `Rabbit` or `Activity` |
| Fastest crash | `Rocket` |
| Killed / dead end | `Skull` |
| Blocked | `ShieldX` |
| Blue patch | `Shield` |
| Useful signal | `Lightbulb` |
| Child / spawn / lineage | `GitBranch` |
| Mutate | `Dna` |
| Retry / replay | `RefreshCw` |
| Terminal/logs | `Terminal` |
| Receipt | `FileJson` |
| Docker replay | `Box` or `Container` |
| Search/research | `Search` |
| Score/winner | `Trophy` |
| Time/playhead | `Clock` |
| Zoom in/out | `ZoomIn`, `ZoomOut` |
| Pan/hand tool | `Hand` |
| Collapse/expand | `ChevronDown`, `ChevronRight` |

## Preserve From Current Kimi Mockup

- Clean lane spacing.
- Strong line readability.
- Sticky time ruler concept.
- Search/filter ergonomics, if they can fit without replacing the original
  left rail.
- Selected exploit detail with streamed log.
- Parent-child row hierarchy.

## Change From Current Kimi Mockup

- Restore the original left spectator rail instead of putting all controls in
  the graph header.
- Restore the standalone Blue Team Control Strip.
- Restore the original footer controls.
- Restore top-right live event list density.
- Do not state that all times are relative to exploit start. Use global race
  time as primary.
- Do not use emoji for production controls.
- Do not make the graph look like a generic table; keep the neon race-board
  presentation from the accepted mockups.

## Standalone HTML Acceptance

The next Kimi deliverable should be:

```text
battle-004-shell-preserving-scroll-timeline.html
```

It must include:

- Standalone HTML/CSS/JS only.
- No external network dependency.
- Clear comments separating visual-only sample density from receipt-backed
  production requirements.
- Demo controls for horizontal scroll and zoom.
- No label/icon overlap at 1920x1080.
- No label/icon overlap at 1440x900.
- Screenshot path or image output for review.

Do not produce React drop-ins until this standalone mockup is visually accepted.

