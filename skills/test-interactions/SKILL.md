---
name: test-interactions
description: >
  Systematic UI interaction testing with screenshots and burst-mode animation capture.
  Generates interaction manifests, captures screenshots via /surf, reviews via /review-design,
  and tracks results on a /create-design-board.
triggers:
  - test interactions
  - test UI interactions
  - interaction testing
  - screenshot test plan
  - test each element
  - burst mode test
  - animation testing
  - interaction manifest
  - test clicking navigation
  - systematic UI test
metadata:
  short-description: Systematic UI interaction testing with screenshots
provides:
  - interaction-testing
  - interaction-manifest
  - burst-capture
composes:
  - surf
  - review-design
  - create-design-board
  - interview
taxonomy:
  - validation
  - precision
  - fragility
---

# test-interactions

Systematic UI interaction testing with screenshot capture and AI review.

Thin GLUE skill that composes `/surf` (capture), `/review-design` (review),
`/create-design-board` (tracking), and `/interview` (ambiguity resolution)
into a repeatable interaction testing workflow driven by a manifest.

## Critical Rule

Screenshots are **acceptance evidence**, not byproducts.

Do not treat `/test-interactions` as "press buttons and save PNGs." The skill is
only complete when the captured images are **critically analyzed** against the
intended target behavior and, when available, against the design reference
surface (existing screenshots, design board, spec, or reference product).

If the screenshot is ugly, ambiguous, off-target, clipped, or otherwise fails to
prove the intended behavior, the interaction test **fails**.

## Required Review Standard

For every meaningful run:

1. Identify the intended target state for the interaction.
2. Capture the state before/after (or burst frames for animation).
3. Inspect the resulting images directly.
4. Compare them against the relevant reference:
   - design board
   - existing approved screenshots
   - competitor/reference product
   - explicit product spec
5. Produce explicit findings:
   - what improved
   - what failed
   - what remains off-target

Do **not** mark success just because:

- a screenshot exists
- pixels changed
- the command ran without error
- a UI element appeared in some ambiguous form

If the image does not clearly support the claim, the claim is unproven.

## Persona Requirement (NON-NEGOTIABLE)

Every visual review MUST specify `--persona`. A review without a persona produces
generic, unfocused feedback that wastes everyone's time. The persona's domain expertise
drives what the review looks for:

- `brandon-bailey` — CMMC/compliance: status indicators, access control, audit trails
- `rob-armstrong` — Formal verification: proof obligations, trust boundaries, Lean4 representation
- `margaret-chen` — Quality assurance: usability heuristics, error handling, edge cases
- `nico-bailon` — Extraction QA: PDF fidelity, table/section verification, quarantine triage, keyboard workflow

```bash
# CORRECT — persona-driven review
./run.sh review --captures ./captures/ --persona brandon-bailey

# CORRECT — full pipeline with persona
./run.sh full --url "http://localhost:3000" --persona rob-armstrong --manifest manifest.json

# WRONG — visual review will be skipped (no persona)
./run.sh review --captures ./captures/
```

## Commands

```bash
# Generate an interaction manifest from a URL or app description
./run.sh generate --url "http://localhost:3000" --output manifest.json

# Run the manifest — capture screenshots for each interaction
./run.sh run --manifest manifest.json --output-dir ./captures/

# Run tests via UX Lab Express test runner (Puppeteer CDP backend)
./run.sh run-server                                    # Run all tests
./run.sh run-server --group design_board               # Run one group
./run.sh run-server --test canvas_card_select          # Run one test
./run.sh run-server --server-url http://localhost:3001  # Custom server URL

# Review captures via /review-design (PERSONA REQUIRED for visual review)
./run.sh review --captures ./captures/ --persona brandon-bailey --output ./INTERACTION_REPORT.md

# Full pipeline: generate → run → review (PERSONA REQUIRED)
./run.sh full --url "http://localhost:3000" --persona rob-armstrong --output-dir ./captures/ --manifest manifest.json
```

## Interaction Manifest Schema

```json
{
  "version": 1,
  "app": "My Dashboard",
  "base_url": "http://localhost:3000",
  "surfaces": [
    {
      "name": "main-dashboard",
      "path": "/",
      "elements": [
        {
          "name": "nav-sidebar",
          "selector": "#sidebar",
          "interactions": [
            {
              "action": "screenshot",
              "description": "Sidebar in default state"
            },
            {
              "action": "click",
              "target": "#sidebar .menu-item:first-child",
              "description": "Click first menu item",
              "screenshot_after": true
            },
            {
              "action": "hover",
              "target": "#sidebar .menu-item:nth-child(2)",
              "description": "Hover second menu item",
              "burst": true,
              "burst_frames": 10,
              "burst_interval_ms": 100
            }
          ]
        }
      ]
    }
  ]
}
```

## Burst Mode (Animation Capture)

For interactions with animations (hover effects, transitions, drag-to-draw),
use `"burst": true` in the interaction. This captures multiple frames that
`/review-design` analyzes as a filmstrip sequence.

Burst frames are stored as `BURST_<element>_<action>_f01.png` through `_f10.png`
in a `burst/` subdirectory, matching `/review-design`'s expected format.

## Workflow

1. **Generate** — Analyze the target app/URL and produce an interaction manifest
2. **Resolve ambiguity** — If the manifest needs human input, `/interview` presents options
3. **Run** — Execute each interaction via `/surf`, capturing screenshots
4. **Review** — Pipe captures to `/review-design` for AI analysis and perform direct human/agent visual critique
5. **Decide** — Treat off-target or ugly captures as failures requiring implementation changes
6. **Track** — Append results to a design board via `/create-design-board`

## Failure Conditions

An interaction run is **not complete** if any of the following are true:

- The manifest does not identify the target state being proven
- The screenshot does not clearly show the intended UI result
- The result is visually worse than the target reference
- The reviewer only reports that "the UI changed" instead of whether it improved
- The capture is ambiguous about which UI surface actually opened
- The test reports success without a findings section grounded in the image

## Recommended Output Per Run

At minimum, record:

- manifest used
- captures produced
- reference used for comparison
- verified behaviors
- failed or ambiguous behaviors
- specific visual defects seen in the screenshot
- concrete next implementation step

## Integration

| Composed Skill | Role |
|----------------|------|
| `/surf` | `surf go`, `surf click`, `surf snap` for browser automation |
| `/review-design` | AI review of captured screenshots + burst filmstrips |
| `/create-design-board` | Track results across rounds in DESIGN_BOARD.md |
| `/interview` | Resolve ambiguous elements or missing selectors |

## Common Mistakes

### WRONG: Running test without specifying --persona for visual review
```bash
./run.sh review --captures ./captures/  # persona missing, visual review skipped
```

### RIGHT: Always specify persona for domain-focused review
```bash
./run.sh review --captures ./captures/ --persona brandon-bailey
```

### WRONG: Treating screenshots as success just because they exist
```bash
./run.sh run --manifest manifest.json --output-dir ./captures/
# "Screenshots captured successfully" — but are they correct?
```

### RIGHT: Critically analyze captures against intended target behavior
```bash
./run.sh run --manifest manifest.json --output-dir ./captures/
./run.sh review --captures ./captures/ --persona brandon-bailey --output REPORT.md
# Report must include: verified behaviors, failed behaviors, visual defects
```

### WRONG: Using burst mode for static UI elements
```json
{"action": "click", "target": "#button", "burst": true, "burst_frames": 10}
```

### RIGHT: Use burst only for animations/transitions
```json
{"action": "hover", "target": "#animated-element", "burst": true, "burst_frames": 10}
```
