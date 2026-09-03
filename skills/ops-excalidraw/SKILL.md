---
name: ops-excalidraw
description: >
  Build and validate Excalidraw whiteboard toolkits for interview strategy diagrams, including reusable finished elements and movable animation tokens that compile into create-svg scene/timeline input. Use when users ask for Excalidraw libraries, whiteboard strategy, animation toolkit items, or Excalidraw-to-create-svg handoff.
triggers:
  - ops-excalidraw
  - Excalidraw toolkit
  - Excalidraw animation tokens
  - whiteboard strategy
  - Excalidraw to create-svg
provides:
  - excalidraw-toolkit
  - excalidraw-validation
  - create-svg-scene-input
composes:
  - create-svg
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-svg-design
runtime_self_improvement: basic
taxonomy:
  - diagramming
  - animation
  - validation
  - developer-tooling
disciplines:
  - ui-design-engineering
  - developer-tooling
---

# Ops Excalidraw

Use this skill to make Excalidraw the movable whiteboard layer and `$create-svg` the compiler/renderer.

## Contract

- Excalidraw owns editable composition: `.excalidraw` boards and `.excalidrawlib` toolkit items.
- Animation intent is represented by visible toolkit tokens with `customData.opsExcalidraw.kind = "animation"`.
- `$create-svg` owns final rendering, CSS animation, reduced-motion base state, SVG safety, and verification.
- This skill emits `$create-svg` scene/timeline JSON; it does not emit final SVG.
- v1 compiles single-source fan-out boards: exactly one `role: "source"` node and one or more `role: "target"` nodes.

## Quickstart (one prompt)

Say `$ops-excalidraw quickstart` (or run the command below). It regenerates the toolkit and serves the whiteboard; open the URL, tick libraries, drag blocks, press **Render SVG**.

```bash
skills/ops-excalidraw/run.sh quickstart --port 7683
```

Accent values on nodes must stay within the create-svg set: cyan, green, amber, orange, red, white.

## Commands

```bash
skills/ops-excalidraw/run.sh toolkit --output /tmp/interview-animation-toolkit.excalidrawlib
skills/ops-excalidraw/run.sh validate skills/ops-excalidraw/fixtures/interview-board.excalidraw
skills/ops-excalidraw/run.sh compile skills/ops-excalidraw/fixtures/interview-board.excalidraw /tmp/interview-scene.yml
skills/create-svg/run.sh render /tmp/interview-scene.yml /tmp/interview.svg
```

## Local whiteboard page

```bash
skills/ops-excalidraw/run.sh whiteboard --port 7683   # open http://127.0.0.1:7683/
```

Embeds the `@excalidraw/excalidraw` component (esm.sh CDN; needs network for first load). Side panel: **Render SVG** button posts the live board to `/render` (compile + `$create-svg` render, SVG shown inline with download link; compile errors shown fail-closed), and library checkboxes load/unload every `.excalidrawlib` under `assets/toolkits/` (generated toolkit + vendored upstream sets).

## Hot reload (live agent changes)

While the whiteboard is open, an agent can push a board and the page applies it live (poll + `updateScene`, ~1.5s):

```bash
skills/ops-excalidraw/run.sh push-board path/to/board.excalidraw --port 7683
```

The push is validated fail-closed before sending; invalid payloads get 422. `GET /board?since=N` returns 204 when current. Human edits in the browser are not overwritten until the next push (last push wins).

## Vendored upstream libraries

The official Excalidraw library directory (libraries.excalidraw.com, github.com/excalidraw/excalidraw-libraries) already ships comprehensive component sets. Three are vendored under `assets/toolkits/vendor/` and validate through this skill (v1 `library` format is normalized automatically):

- `system-design.excalidrawlib` (rohanp, 24 items: LB, queue, cache, DB, CDN, etc.)
- `software-architecture.excalidrawlib` (youritjang, 7 items)
- `decision-flow-control.excalidrawlib` (aretecode, 8 items)

Import them into Excalidraw alongside the generated toolkit for visual vocabulary; use the generated toolkit's tagged nodes/tokens for anything that must compile through `$create-svg`.

## Toolkit model

Use normal Excalidraw library items for finished visual blocks:

```json
{"customData":{"opsExcalidraw":{"kind":"node","role":"target","title":"Evidence case","detail":"source-bound","accent":"green"}}}
```

Use visible animation tokens for reusable motion:

```json
{"customData":{"opsExcalidraw":{"kind":"animation","preset":"glow-pulse","targetId":"source","startMs":1200,"durationMs":900}}}
```

Supported animation presets:

- `reveal` → `$create-svg` `fade-slide-y`
- `line-draw` → `$create-svg` `draw-stroke`
- `glow-pulse` → `$create-svg` `halo-pulse`
- `highlight` → `$create-svg` `color-pin`
- `pulse` → `$create-svg` `pulse`

## Binding rule

1. Prefer explicit `targetId` in the animation token.
2. Otherwise bind to a node-tagged element in the same Excalidraw group.
3. Otherwise bind to the single overlapping node-tagged element.
4. Otherwise fail closed; do not guess.

## Finalization

After compile, run `$create-svg` Stage 1 render/preview. Only after approval, run `$create-svg verify --receipt --browser` and keep the receipt with the final SVG.
