# ops-excalidraw — Immutable Goal

/ goal A local, offline, fast whiteboard for live meetings and interviews: the
human sketches strategy in stock Excalidraw with professional libraries
pre-loaded, the project agent can push charts and custom library items and
render any board to a verified SVG artifact, and the two Excalidraw and
create-svg jobs stay separated (Excalidraw owns editable composition,
create-svg owns final render/animation/verification).

## Primary proof

- `skills/ops-excalidraw/run.sh render-board skills/ops-excalidraw/fixtures/meeting-scenario-board.excalidraw --output /tmp/ops-excalidraw-goal.svg`
  exits 0, emits `ops_excalidraw.render_board.v1 status PASS`, and writes a
  non-empty `<svg …>` file.
- `skills/agentic-evals/run.sh run skills/ops-excalidraw/fixtures/agentic_eval.json --output /tmp/ox-eval.json`
  reports `readiness: READY` with zero FAIL/BLOCKED/NOT_TESTED.

## Completion criteria

- `quickstart` serves the offline whiteboard (no CDN) with every library under
  `assets/toolkits/` pre-loaded and browsable via the native Library button.
- The agent can `push-board` a chart (applied live) and `push-library` custom
  items (persisted by id-merge, never dropping prior personal items).
- Any board compiles + renders through create-svg to an SVG, fail-closed on
  invalid input (malformed JSON, unknown customData kind, invalid accent,
  garbage HTTP payload, path traversal).
- A human's in-progress canvas is never silently destroyed: an agent push must
  not steal the viewport on live updates, and personal-library saves must not
  drop existing items.
- Every new feature carries a retained `$agentic-evals` case; the fixture stays
  READY.

## Allowed scope

- `skills/ops-excalidraw/**` (server, page, toolkit compiler, vendored assets,
  fixtures) and its create-svg integration seam.

## Forbidden drift

- Forking Excalidraw. Rebuilding features Excalidraw already ships natively
  (PNG export, background swatches, zoom-to-fit, alignment, grid toggle).
  Multi-user collaboration servers. Dashboards or review theater not backed by
  a passing proof command.

## Retry/stop rule

- If the primary proof still fails after 2 focused attempts on the same
  blocker, stop and write a blocker report with the failed command, its output,
  changed files, artifact paths, current hypothesis, and one recommended next
  action.

## Assumptions (labeled, 2026-09-04)

- No prior `immutable_goal.json` existed; this goal is inferred from the
  operator's stated intent across the build session ("fast/easy/dynamic way to
  whiteboard strategy in live meetings, professional libraries ready, agent
  hot-reload, render to SVG") plus the SKILL.md contract.
- v1 hot-reload is last-push-wins. The safe-copilot end state (proposal-first
  push with Accept/Reject against a base revision, per the WebGPT review's
  P0.2) is the next major milestone toward this goal, not part of the v1 proof.
