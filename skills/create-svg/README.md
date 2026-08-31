# README SVG Animator

A Python-native skill for producing self-contained animated SVG diagrams that work in
GitHub README `<img>` elements. It separates reusable visual tokens from semantic scene
content and animation timing, so a consistent README style does not require hand-editing
thousands of SVG coordinates and keyframe percentages.

## Included

- `fixing-opus-neon-v1` visual theme: Play/JetBrains Mono font stacks, dark GitHub-like
  background, cyan/green/amber/red/orange accents, rounded cards, drop shadows, and the
  3-second / 12-second animation vocabulary used by the reference README.
- `positive-negative` and `fanout-anatomy` semantic templates.
- CSS recipes for fade, slide, normalized stroke drawing, color pinning, and halo pulses.
- Pydantic scene/theme validation, safe YAML loading, structured XML generation, and
  README-safe SVG validation.
- Real Chromium `<img>`-mode motion verification when `--browser` is requested.
- Screenshot-bound `visual-gate` receipts for target-size visual acceptance.
- Tau-backed `tau-variant-loop` planning for N concurrent creator variants plus an independent judge.
- `tau-provenance-gate` receipts that prevent local preview SVGs from being published as Tau winners without Tau node receipts and screenshot-bound visual-gate PASS.
- Component grouping contracts for downstream consumers that need stable labels, cards, nodes, pills, and visual bounds.
- A deterministic JSON receipt and an agentic-evals fixture.

No upstream SVG artwork and no font binaries are included.

## Quick start

```bash
cd skills/create-svg
uv sync --group dev

./run.sh new positive-negative /tmp/scene.yml
./run.sh render /tmp/scene.yml /tmp/scene.svg
./run.sh verify /tmp/scene.yml /tmp/scene.svg \
  --receipt /tmp/scene.receipt.json --browser
./run.sh preview /tmp/scene.svg /tmp/scene-preview.html
```

Insert the generated image with:

```html
<p align="center">
  <img src="images/scene.svg" alt="Describe the diagram" width="850">
</p>
```

## Scene model

```yaml
schema_version: 1
theme: fixing-opus-neon-v1
template: positive-negative
metadata:
  title: Validation contract
  description: Behaviors the artifact must replicate and avoid
left:
  heading: REPLICATE
  accent: green
  items:
    - Typed input schema
    - Deterministic output
right:
  heading: AVOID
  accent: red
  items:
    - Unverified screenshots
    - External SVG dependencies
caption: GENERATE, VERIFY, THEN PUBLISH
timeline:
  cycle_ms: 3000
  events:
    - target: left-glow
      recipe: halo-pulse
      start_ms: 0
      end_ms: 3000
      peak_opacity: 0.35
```

The compiler converts each millisecond boundary to a percentage of `cycle_ms`, creating
one synchronized CSS loop. Connector paths use `pathLength="1"`, so every draw-on recipe
animates `stroke-dashoffset` from `1` to `0` without calculating physical path lengths.

## Commands

| Command | Purpose |
|---|---|
| `templates` | List available semantic scene templates. |
| `new` | Copy a starter scene. |
| `render` | Validate YAML and generate deterministic SVG. |
| `verify` | Render twice, compare digests, validate, and optionally run Chromium. |
| `validate` | Validate an existing SVG and emit a receipt. |
| `inspect` | Extract colors, fonts, strokes, viewBoxes, and animation signatures. |
| `preview` | Create a self-contained local HTML viewer. |
| `snippet` | Print centered README `<img>` markup. |
| `visual-gate` | Fail closed unless a reviewer inspected the exact screenshot path and SHA256. |
| `tau-visual-loop` | Build or run a sequential Tau creator/reviewer SVG loop. |
| `tau-variant-loop` | Build or run a Tau compete DAG with N concurrent creator variants. |
| `tau-provenance-gate` | Fail closed unless a proposed Tau winner binds launch, run, node, candidate, screenshot, and visual-gate receipts. |
| `failure-codes` | Print exact `create_svg_*` codes consumed by `$triage-error`. |

## Tau variant exploration

Use `tau-variant-loop` when the right visual direction is unknown. The variant
pack is explicit and reproducible; each variant becomes one concurrent Tau
creator node, and the judge cannot accept a winner without screenshot-bound
`visual-gate` proof.

```yaml
schema: create_svg.variant_pack.v1
variants:
  - id: ledger-first
    direction: Make signed receipts and the append-only ledger visually dominant.
  - id: dag-first
    direction: Make DAG nodes and enforced edges visually dominant.
```

```bash
./run.sh tau-variant-loop variants.yml \
  --goal "Tau is a zero-trust DAG execution harness" \
  --target "grahama.co Tau project card" \
  --target-size "400x260" \
  --screenshot-command 'skills/surf/run.sh screenshot --out <SCREENSHOT_PATH>' \
  --creator-handler gpt-5.5-high \
  --creator-handler webkimi \
  --judge-handler claude-fable-low \
  --receipt /mnt/storage12tb/skills/create-svg/outputs/tau-variants/plan.json
```

If a receipt has `code: create_svg_visual_gate_not_ready`, treat it as design-loop
feedback. Runtime or contract failures must carry another exact `create_svg_*`
code so `$triage-error classify --receipt <path> --layer create-svg` does not
need to parse prose.

## Development

```bash
./sanity.sh
```

The sanity runner uses the project's `uv` environment, executes real behavior rather than
mocks, proves unsafe input fails closed, and invokes the repository skill validator when
installed beside `best-practices-skills`.
