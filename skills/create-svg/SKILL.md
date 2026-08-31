---
name: create-svg
description: >
  Create, restyle, preview, and validate self-contained themed SVG diagrams and
  animations for any surface — READMEs, websites, pitchdecks, docs, artifacts.
  Use when a user asks for an animated SVG, an animated README SVG, a reusable
  SVG style preset, a dark neon technical diagram, deterministic CSS-keyframe
  animation, or a README-safe SVG generated from a semantic scene. README-grade
  constraints (no JS, self-contained, reduced-motion fallback) are the universal
  floor, which makes every artifact portable to less-hostile surfaces for free.
triggers:
  - animated README SVG
  - create SVG animation
  - copy SVG visual style
  - generate README diagram
  - dark neon technical graphic
  - extract SVG theme
provides:
  - animation-vocabulary
  - design-engineering-guidance
  - animation-review
composes:
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
taxonomy:
  - animation
  - svg
  - readme
  - developer-tooling
runtime_self_improvement: basic
metadata:
  short-description: Deterministic GitHub README SVG animation generator
  python_versions: ["3.11+", "3.12+", "3.13+"]
---

# README SVG Animator

Create GitHub-compatible animated SVG illustrations from three explicit inputs:

1. **Theme** — fonts, palette, stroke widths, shadows, radii, and timing defaults.
2. **Scene** — semantic content using a bounded diagram template.
3. **Timeline** — millisecond events compiled into one synchronized CSS cycle.

The shipped `fixing-opus-neon-v1` theme reproduces the visual vocabulary of the
MIT-licensed `disler/fixing-smartass-opus-5` README assets without bundling its
SVG artwork or any font binaries.

## Use this skill when

- A README needs an animated hero, comparison card, or technical diagram.
- A user wants the same font, color, stroke, shadow, and timing language across assets.
- SVG output must remain self-contained and work through a README `<img>` element.
- A style must be extracted from existing SVG files before generating new scenes.

Do not use it for raster illustration, interactive JavaScript visualization, or
arbitrary untrusted HTML. It deliberately rejects scripts, event handlers,
`foreignObject`, external URLs, DTDs, and unresolved references.

## Workflow — two stages, never one-shot

Stage 1 (**draft**): author or edit the scene YAML, `render`, and show the human the
real animated SVG — in a Chrome browser tab (serve the file over localhost; the
browser extension rejects `file://`) or via `preview`. The draft render costs about a
second and is deterministic, so the actual SVG is the design preview; do not
substitute a chart approximation of it. Iterate on labels, palette, and timeline
here until the human approves.

Stage 2 (**finalize**): only after approval, run `verify --receipt --browser`, keep
the receipt with the artifact, and emit the README `snippet`. Never present a
Stage-1 draft as the deliverable.

```bash
SKILL_DIR=skills/create-svg

# See the available semantic templates.
"$SKILL_DIR/run.sh" templates

# Copy a starter scene, then edit its labels and timeline.
"$SKILL_DIR/run.sh" new positive-negative ./scene.yml

# Compile deterministic SVG.
"$SKILL_DIR/run.sh" render ./scene.yml ./images/scene.svg

# Verify deterministic rebuild, structure, theme, and optional browser motion.
"$SKILL_DIR/run.sh" verify ./scene.yml ./images/scene.svg \
  --receipt ./scene.receipt.json --browser

# Emit README markup without editing README.md automatically.
"$SKILL_DIR/run.sh" snippet ./images/scene.svg \
  --alt "Validation behaviors to replicate and avoid" --width 850
```

To inspect an existing SVG corpus:

```bash
"$SKILL_DIR/run.sh" inspect ./upstream/images --output ./style-inspection.yml
```

To explore several slightly different directions through Tau, create an explicit
variant pack and compile a compete DAG. This creates N concurrent creator nodes,
one per handler/variant, then routes their outputs to a judge/reviewer stage. It
is not a local render batch and it must not close without screenshot-bound
`visual-gate` proof.

```yaml
# variants.yml
schema: create_svg.variant_pack.v1
variants:
  - id: ledger-first
    direction: Make signed receipts and the append-only ledger visually dominant.
  - id: dag-first
    direction: Make DAG nodes and enforced edges visually dominant.
  - id: reviewer-first
    direction: Make creator/reviewer/human gate sequence visually dominant.
```

```bash
"$SKILL_DIR/run.sh" tau-variant-loop variants.yml \
  --goal "Tau is a zero-trust DAG execution harness" \
  --target "grahama.co Tau project card" \
  --target-size "400x260" \
  --screenshot-command 'skills/surf/run.sh screenshot --out <SCREENSHOT_PATH>' \
  --creator-handler gpt-5.5-high \
  --creator-handler webkimi \
  --creator-handler webgemini \
  --judge-handler claude-fable-low \
  --receipt /mnt/storage12tb/skills/create-svg/outputs/tau-variants/plan.json
```

## Decision map

| Need | Command | Read next |
|---|---|---|
| Start from a known layout | `new` | `references/schema.md` |
| Generate an SVG | `render` | `references/readme-image-constraints.md` |
| Extract another visual system | `inspect` | `references/style-extraction.md` |
| Prove an artifact is safe and deterministic | `verify` | receipt JSON |
| Validate an existing SVG only | `validate` | finding codes in receipt |
| See the animation locally | `preview` | generated HTML file |
| Explore several directions concurrently | `tau-variant-loop` | Tau receipt + screenshots |
| Gate screenshot-reviewed visual acceptance | `visual-gate` | `create_svg.visual_gate.v1` receipt |
| Prove a Tau variant winner is publishable | `tau-provenance-gate` | `create_svg.tau_variant_provenance_gate.v1` receipt |

## Non-negotiable contracts

- Output is SVG/XML with embedded CSS only; no JavaScript or external resources.
- YAML is loaded with `safe_load` and validated through Pydantic before rendering.
- SVG is created with XML builders, not string-concatenated user markup.
- The complete final composition is the base state. Animation is enabled only inside
  `@media (prefers-reduced-motion: no-preference)`.
- Timeline offsets are millisecond values compiled into percentages of one cycle.
- A producer emits either a validated PASS receipt or a non-zero failure.
- Component-oriented outputs should mark meaningful grouped elements with stable `id`/`data-component` metadata so downstream checks can target the top visual group instead of loose decorative primitives.
- Deterministic repairs are narrow and explicit; this MVP does not silently repair input.
- Font family names are emitted, but font files are never included. Exact-font mode must
  receive a separately licensed local font from the operator in a future extension.
- Generated previews, browser frames, and receipts should be written beneath
  `/mnt/storage12tb/skills/create-svg/` in the full agent-skills environment.
- Tau variant-loop failures must surface exact `create_svg_*` failure codes in
  receipts so `$triage-error classify --receipt <path> --layer create-svg` can
  route the failure without regexing reviewer prose. `create_svg_visual_gate_not_ready`
  is normal design-loop control, not a runtime defect.

## Verification posture

`sanity.sh` runs unit tests plus real render, XML validation, README-image browser
verification, and a negative unsafe-SVG gate. It also runs the repository's current
`best-practices-skills/scripts/validate_skill.py` when that sibling skill exists.

The agentic-evals fixture is `fixtures/agentic_eval.json`:

```bash
./skills/agentic-evals/run.sh run \
  skills/create-svg/fixtures/agentic_eval.json \
  --output /mnt/storage12tb/skills/create-svg/outputs/agentic-eval.json
```

A skipped browser check is `NOT_RUN`, not PASS. A missing adjacent repository validator
is also reported as `NOT_RUN`; the bundled contract checker still executes.

## Failure recovery

| Failure | Required action |
|---|---|
| Scene validation fails | Correct the named YAML field; do not bypass Pydantic. |
| Unsafe SVG finding | Remove the forbidden element, attribute, URL, DTD, or reference. |
| Theme contract fails | Use a declared theme token or disable strict theme intentionally. |
| Browser motion is not observed | Open the preview, inspect reduced-motion state and CSS targeting, then re-render. |
| Deterministic rebuild differs | Treat as a compiler defect; do not publish either artifact. |
| Font appearance differs | Install the named OFL font locally or accept the declared fallback stack. |

## Output contract

Successful `verify` emits:

- the deterministic `.svg` artifact;
- a `readme-svg-validation.v1` JSON receipt;
- optional real-browser evidence when `--browser` is selected.

The receipt states what was proved and what was not proved. Never present a preview
screenshot alone as evidence that the SVG is safe, deterministic, or README-compatible.
