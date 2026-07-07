# Battle-004 Kimi Render Review

## Status

The revised standalone Kimi mockup was rendered and inspected. It is closer to
the accepted shell than the prior iteration, but it is still not ready for React
implementation because the center race graph loses lane identity and event
readability.

Rendered source:

```text
/tmp/battle-kimi-render-20260704T1750/source.html
```

Rendered screenshots:

```text
/tmp/battle-kimi-render-20260704T1750/1920x1080.png
/tmp/battle-kimi-render-20260704T1750/1440x900.png
```

CDP marker:

```text
/tmp/codex-ui-verification/pi-mono/battle-kimi-race-dashboard-render-review/20260704T175431Z.png
```

## Render Evidence

Automated metrics:

```text
1920x1080:
  lanes: 11
  clipped text elements: 0
  center graph: x=288 y=270 width=1244 height=718
  left rail width: 260
  detail pane width: 360
  footer height: 64

1440x900:
  lanes: 11
  clipped text elements: 0
  center graph: x=288 y=270 width=764 height=538
  left rail width: 260
  detail pane width: 360
  footer height: 64
```

The clipping count is not the acceptance signal here. The visual failure is
semantic: at both viewports, especially 1440x900, the center graph appears as
mostly unlabeled horizontal lines. The user cannot quickly tell what each
exploit is doing.

## What Improved

- Header, Blue Team Control Strip, left rail, right pane, and footer were
  restored structurally.
- Right pane includes `AGENT DETAIL` and a visible Docker replay affordance.
- The mockup has a horizontal timeline and zoom controls.
- The overall dark acrylic visual language is closer than the prior two-column
  mockup.

## Blocking Visual Issues

1. **Center graph loses lane identity**
   - At 1440x900 the graph shows mostly red lines with no visible lane names.
   - Sticky lane labels are not visibly helping the viewer understand rows.
   - The left rail is not a substitute for row labels in the race graph.

2. **Initial scroll hides story context**
   - The first visible ruler region starts around T+10.
   - Early lane start/spawn/materialization context is absent.
   - The user cannot see how the race begins without manually scrolling.

3. **Event labels are too sparse or off-screen**
   - The mockup no longer shows the dense phase/action text from the accepted
     references.
   - Required visible phases include research, payload, mutate, retry, trigger,
     observe, useful signal, block, killed, promoted, fastest crash, and
     receipt.

4. **Blue interventions are weak in the graph**
   - The Blue strip exists, but the center graph does not strongly show Blue
     interventions as visible shield/burst events connected to affected lanes.

5. **Right pane hierarchy needs tightening**
   - `AGENT DETAIL` is visible, but selected exploit name should be more
     prominent.
   - The selected exploit header should read as:

     ```text
     AGENT DETAIL
     REPLAY FORK
     payload-857-A · Gen 2 · FASTEST CRASH
     ```

6. **Header crowding at 1440px**
   - The top-right live event panel crowds the header/score area.
   - At 1440px, reduce visible feed rows or make the header slots more
     disciplined.

## Required Kimi Changes

Ask Kimi to revise the standalone HTML/CSS/JS mockup with these corrections:

```text
1. Keep lane names visible in the center graph at all horizontal scroll
   positions. The center graph itself must show Archive Escape, Replay Fork,
   Tar Tunnel, Boundary Fray, and child lanes next to their lines.

2. Do not auto-scroll the graph so the initial view starts near T+10. Initial
   view must show T+0 and the first spawn/materialization events. If centering
   on active action, preserve enough left context to understand lane starts.

3. Restore dense race-board row content:
   - exploit name
   - generation
   - payload id
   - runner icon
   - phase labels
   - event markers
   - terminal outcomes
   - receipt/proof markers

4. Use label bands for each lane:
   - top band: RESEARCH, PAYLOAD, MUTATE, RETRY, TRIGGER
   - center: runner/progress line and major markers
   - bottom band: BLOCKED, KILLED, FASTEST CRASH, PROMOTED

5. Make Blue interventions strong in the graph:
   - shield/burst visual
   - blue connector or vertical intervention line
   - label such as BLOCKED -> HANDOFF, PATCH GATE, or BLUE BLOCK
   - no overlap with red exploit labels

6. Keep the original shell proportions:
   - left rail: about 260px
   - right pane: about 360px
   - Blue strip: about 72px
   - footer: about 64px
   - center graph consumes the remaining width

7. Improve right-pane selected exploit hierarchy:
   AGENT DETAIL
   REPLAY FORK
   payload-857-A · Gen 2 · FASTEST CRASH
   Docker replay remains visible.

8. At 1440x900, the header live feed must not crowd or cover the score block.
   Use two visible rows plus overflow if needed.

9. Use Lucide-compatible icon names in comments/component plan:
   Bug, Rocket, Skull, Shield, ShieldX, Lightbulb, GitBranch, Dna,
   RefreshCw, Terminal, FileJson, Box, Search, Clock, ZoomIn, ZoomOut.

10. Return a new standalone HTML file plus screenshot renders at 1920x1080 and
    1440x900. Do not return React drop-ins until this standalone mockup passes
    visual review.
```

## Acceptance For Next Mockup

- Original Battle shell remains recognizable.
- Center graph communicates what each exploit is doing without relying on the
  left rail.
- Lane names remain visible during horizontal scroll.
- Event labels are dense enough to match the accepted mockups.
- No event label overlaps an icon or another label.
- Docker Replay remains visible in the right pane.
- Horizontal scroll and zoom controls are usable.
- Child lanes start at parent handoff/spawn time.
- Parent-child connectors originate from the handoff/spawn event.

