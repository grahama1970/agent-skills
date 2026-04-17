---
name: test-interactions
description: >
  Deterministic UI interaction testing against LIVE DOM via CDP.
  All interactions target [data-qid] selectors. PASS/FAIL from thresholds, not LLM.
  Batched VLM review at the end only — never in the test loop.
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
  - cots compliance test
  - qid compliance
metadata:
  short-description: Deterministic UI interaction testing with COTS compliance
provides:
  - interaction-testing
  - interaction-manifest
  - burst-capture
  - qid-compliance
  - cots-assertions
composes:
  - surf
  - review-design
  - create-design-board
  - interview
  - best-practices-react
  - best-practices-cots
taxonomy:
  - validation
  - precision
  - fragility
---

# test-interactions

Deterministic UI interaction testing against the LIVE DOM via CDP.

## PREREQUISITE: Read /best-practices-react FIRST

Before writing ANY manifest or running ANY test, you MUST read
`.pi/skills/best-practices-react/SKILL.md`. It defines:

- The **4-attribute rule**: every interactive element needs `data-qid`,
  `data-qs-action`, `title`, and `useRegisterAction`
- QID naming conventions (`component:element:qualifier`)
- How to verify qid coverage with `verify-data-qid.py`

If you skip this, your manifests will target the wrong selectors and
miss compliance requirements. This is not optional.

## Architecture: Deterministic Run, Batched LLM Review

```
RUN stage (deterministic — no LLM)
├── CDP interactions: click, type, key, tab, scroll, wait
├── DOM assertions: selector, visible, text, value, attribute, aria
├── COTS assertions: min_size (C02), font_size (C01), contrast (C03),
│   title (C14), focus_visible (C06)
├── QID compliance scan: 4-attribute rule on all [data-qid] elements
└── PASS/FAIL verdicts from thresholds and DOM state

REVIEW stage (one batched LLM call at the end)
├── vlm_image preprocessing: auto-crop, sharpen, upscale, stitch
├── /review-design with REQUIRED --persona
└── Visual critique of captured screenshots (does NOT change verdicts)
```

The LLM never decides pass/fail. It only comments on evidence after
deterministic tests have already run.

## Critical Rules

### 1. All selectors MUST be [data-qid]

No `#id`, no `.class`, no `nth-child`, no XPath. Every interaction targets
a `[data-qid='...']` selector. If an element doesn't have a `data-qid`,
that's a bug in the component — fix it first.

### 2. Persona is REQUIRED (non-negotiable)

Every `review` and `full` command MUST specify `--persona`. The CLI will
reject the command without one. A review without a persona produces generic,
unfocused feedback that wastes everyone's time.

Available personas:
- `brandon-bailey` — CMMC/compliance: status indicators, access control, audit trails
- `rob-armstrong` — Formal verification: proof obligations, trust boundaries
- `margaret-chen` — Quality assurance: usability heuristics, error handling, edge cases
- `nico-bailon` — Extraction QA: PDF fidelity, table verification, keyboard workflow

### 3. Every LIVE DOM interactive component must be tested

If it's in the DOM and it's interactive (button, link, input, select, tab),
it must appear in a manifest and have assertions against it.

## Commands

```bash
# Generate an interaction manifest from a URL
./run.sh generate --url "http://localhost:3000" --output manifest.json

# Run the manifest — deterministic CDP + assertions → PASS/FAIL
./run.sh run --manifest manifest.json --output-dir ./captures/

# Review captures — PERSONA REQUIRED
./run.sh review --captures ./captures/ --persona brandon-bailey

# Full pipeline: generate → run → review — PERSONA REQUIRED
./run.sh full --url "http://localhost:3000" --persona rob-armstrong --manifest manifest.json

# Run tests via UX Lab Express test runner (Puppeteer CDP backend)
./run.sh run-server
./run.sh run-server --group design_board
./run.sh run-server --test canvas_card_select
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
      "wait_ready": "[data-qid='dashboard:header']",
      "qid_compliance": true,
      "elements": [
        {
          "name": "nav-sidebar",
          "interactions": [
            {
              "action": "screenshot",
              "description": "Sidebar in default state"
            },
            {
              "action": "click",
              "target": "[data-qid='nav:item:home']",
              "description": "Click home nav item",
              "screenshot_after": true,
              "assert_title": "[data-qid='nav:item:home']",
              "assert_qs_action": "[data-qid='nav:item:home']",
              "assert_min_size": {"selector": "[data-qid='nav:item:home']", "min_width": 44, "min_height": 44}
            },
            {
              "action": "tab",
              "count": 3,
              "description": "Tab through nav items, verify focus path",
              "assert_focus_visible": "[data-qid='nav:item:settings']"
            },
            {
              "action": "key",
              "key": "Enter",
              "description": "Activate focused nav item with Enter"
            }
          ]
        }
      ]
    }
  ]
}
```

## Actions

| Action | Description | Key Fields |
|--------|-------------|------------|
| `screenshot` | Capture current state | `description` |
| `click` | Click a [data-qid] element | `target` (required) |
| `type` | Type into a [data-qid] input | `target`, `value` |
| `wait` | Wait for element to appear | `target`, `timeout_ms` |
| `scroll` | Scroll page | `direction`, `amount` |
| `key` | Press a keyboard key | `key` (Tab, Enter, Escape, Space, Arrow*) |
| `tab` | Tab N times, track focus path | `count` (default 1) |

## Assertions (Deterministic)

### Standard DOM assertions

| Assertion | Description |
|-----------|-------------|
| `assert_selector` | Element exists in DOM |
| `assert_visible` | Element visible (not hidden/zero-size) |
| `assert_text` | Text content matches |
| `assert_absent` | Element NOT in DOM |
| `assert_count` | Element count in {min, max} range |
| `assert_attribute` | Element attribute value |
| `assert_css` | Computed CSS property |
| `assert_value` | Input/select current value |
| `assert_url` | Current page URL |
| `assert_enabled` / `assert_disabled` | Interactive element state |
| `assert_aria` | ARIA attribute value |

### COTS compliance assertions

| Assertion | COTS Rule | Threshold |
|-----------|-----------|-----------|
| `assert_min_size` | C02 touch targets | >= 44x44px (WCAG 2.1) |
| `assert_font_size` | C01 font size | >= 12px (MIL-STD-1472H) |
| `assert_contrast` | C03 color contrast | >= 4.5:1 (WCAG 2.1 AA) |
| `assert_title` | C14 tooltips | title attribute exists |
| `assert_focus_visible` | C06 focus indicator | outline or boxShadow visible |

### QID compliance assertions

| Assertion | Description |
|-----------|-------------|
| `assert_qs_action` | Element has `data-qs-action` attribute |
| `assert_title` | Element has `title` attribute |

### Per-surface QID compliance scan

Enabled by default (`qid_compliance: true`). After all interactions on a surface,
scans every `[data-qid]` element for:

- Missing `title` on interactive elements
- Missing `data-qs-action` on interactive elements
- Touch target < 44x44px on interactive elements

Set `"qid_compliance": false` on a surface to skip.

## VLM Image Preprocessing

Before the batched LLM review, screenshots are preprocessed with `vlm_image.py`:

- **auto_crop** — Trim dark borders from headless Chrome captures
- **sharpen_text** — Enhance text edges for VLM OCR accuracy
- **upscale** — Scale small images to 1200px width for readability
- **compress** — Convert to JPEG if exceeds 500KB
- **stitch_vertical** — Stack burst frames into single filmstrip

Use `--no-preprocess` to skip.

## Burst Mode (Animation Capture)

For interactions with animations, use `"burst": true`. Captures multiple frames
that get stitched into a filmstrip for the VLM review.

```json
{"action": "hover", "target": "[data-qid='animated:element']", "burst": true, "burst_frames": 10}
```

## Workflow

1. **Read /best-practices-react** — Understand qid conventions and 4-attribute rule
2. **Generate** — Analyze target app and produce manifest with [data-qid] selectors
3. **Run** — Deterministic CDP interactions + assertions → PASS/FAIL
4. **Review** — Batch screenshots to /review-design with persona → visual critique
5. **Decide** — Off-target or ugly captures are failures requiring implementation changes

## Common Mistakes

### WRONG: Running without reading /best-practices-react first
```bash
./run.sh full --url "..." --persona brandon-bailey
# Manifest uses #id and .class selectors — all wrong
```

### RIGHT: Read /best-practices-react, then build manifest with [data-qid] selectors
```bash
# 1. Read .pi/skills/best-practices-react/SKILL.md
# 2. Build manifest with [data-qid='component:element:qualifier'] selectors
# 3. Run
./run.sh full --url "..." --persona brandon-bailey --manifest manifest.json
```

### WRONG: Running review without persona
```bash
./run.sh review --captures ./captures/
# ERROR: --persona is required
```

### WRONG: Using CSS selectors that aren't [data-qid]
```json
{"action": "click", "target": "#sidebar .menu-item:first-child"}
```

### RIGHT: All selectors are [data-qid]
```json
{"action": "click", "target": "[data-qid='nav:item:home']"}
```

### WRONG: Relying on LLM to decide pass/fail
```bash
# "Ask the VLM if the button looks correct" — NO
```

### RIGHT: Deterministic assertions decide pass/fail
```json
{
  "action": "click",
  "target": "[data-qid='nav:item:home']",
  "assert_min_size": {"selector": "[data-qid='nav:item:home']", "min_width": 44, "min_height": 44},
  "assert_title": "[data-qid='nav:item:home']",
  "assert_qs_action": "[data-qid='nav:item:home']"
}
```

## Integration

| Composed Skill | Role |
|----------------|------|
| `/best-practices-react` | MUST READ FIRST — qid conventions, 4-attribute rule |
| `/best-practices-cots` | COTS thresholds (C01-C15), scanner.cjs reference |
| `/surf` | `surf go`, `surf click`, `surf snap` for browser automation |
| `/review-design` | AI review of captured screenshots (batched, end only) |
| `/create-design-board` | Track results across rounds in DESIGN_BOARD.md |
| `/interview` | Resolve ambiguous elements or missing selectors |
