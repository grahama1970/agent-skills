# Handoff: monitor-website / grahama.co memory card (supersedes 2026-08-27 16:30 version)

**Timestamp**: 2026-08-27 18:00-04:00
**State**: spacing + ink fixes LANDED, committed on local main, live on 127.0.0.1:3020.

## What changed this session (all committed; DO NOT push — divergent vs origin)

- `spacing` default check now enforces the real law: **uniform inter-row gaps +
  symmetric margins** (center-rhythm informational). The old card FAILED it at
  gaps [72,68,68,90,104,86] — that was the human's "not evenly spaced" defect.
- `pixels` check: painted bands must land inside manifest row spans
  (`pixels <png> --manifest <grid.json>`).
- New `place` command + `scripts/place_grid.py`: rows placed mechanically from
  the machine-readable manifest; supports per-row absolute `label_offset`
  baselines. THE lawful way to move anything — hand-nudges (sed on coords) are
  forbidden; one was made and reverted this session (c97c4c1284 → 77819f4d2a).
- memory-recall-card: 74px uniform gaps, 100px margins, connectors re-anchored
  (10px clearances, flush tips), connector ink unified
  (.base-path rgba cream 0.32, arrowhead 0.62), outcome pill borders raised
  (clarify 0.45, panel-soft 0.30). Response label baseline +5px via manifest
  `label_offset: 58` (absolute baseline from response row top).
- Site rebuilt; served page references `?v=c8b8b04eaa` (inventory versions from
  the asset commit — a rebuild after any card commit is MANDATORY or browsers
  pin stale bytes; this caused a "no changes" false alarm mid-session).

## Verified (re-run before claiming)

- `run.sh spacing|grid|validate|pixels --manifest` all green
- live-DOM gaps measured via surf js in the human's tab: 23.4×6px, margins 31.7
- post-build `curl explore.html` shows the new ?v=<commit>

## What remains

1. G9 human acceptance (human last saw the final state and responded "great" to
   the ink deploy; the label_dy + final snap were not human-reviewed).
2. Agentic-eval fixture has new cases (uneven/uniform gaps, manifest pixels);
   last full run was USABLE_WITH_GAPS before the shifted-row fixture was
   updated — re-run `skills/agentic-evals/run.sh run
   skills/best-practices-svg-design/fixtures/agentic_eval.json`.
3. Full cascade + push + deploy still unrun (unchanged from previous handoff).
