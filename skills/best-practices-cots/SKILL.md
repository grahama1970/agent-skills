---
name: best-practices-cots
description: >
  Automated COTS defense UX compliance scanner. Tests against WCAG 2.1 AA, Section 508,
  MIL-STD-1472H, and NIST 800-53 UI controls via CDP interaction + VLM visual analysis.
triggers:
  - check cots compliance
  - accessibility audit
  - defense ux review
  - section 508 check
  - wcag compliance scan
  - mil-std-1472 review
  - cots acceptance test
composes:
  - common/vlm_image.py
  - scillm
provides:
  - cots-compliance-report
  - cots-fix-plan
disciplines:
  - engineering-standards
  - compliance-security
  - ui-design-engineering
---

# /best-practices-cots

Automated COTS defense UX compliance scanner. Tests UI components against
mandatory government/defense standards via CDP headless Chrome + VLM visual analysis.

## What It Checks

| # | Rule | Standard | Method |
|---|------|----------|--------|
| C01 | Body text ≥ 16px | MIL-STD-1472H | CDP: `getComputedStyle().fontSize` on all text nodes |
| C02 | Touch targets ≥ 44x44px | WCAG 2.1 / Apple HIG | CDP: `getBoundingClientRect()` on all `[data-qid]` interactive elements |
| C03 | Color contrast ≥ 4.5:1 (AA) | WCAG 2.1 | CDP: computed foreground/background colors → WCAG contrast formula |
| C04 | Color not sole information carrier | WCAG 2.1 | VLM: crop status indicators, ask "can you determine meaning without color?" |
| C05 | Full keyboard navigation | Section 508 | CDP: Tab through all interactive elements, verify focus order |
| C06 | Visible focus indicator | Section 508 | CDP: trigger focus on elements, screenshot, VLM: "is focus ring visible?" |
| C07 | Acronyms expanded on first use | MIL-STD-1472H | VLM: crop text areas, ask "are all acronyms defined?" |
| C08 | Metrics labeled with units/definition | MIL-STD-1472H | VLM: crop metric displays, ask "is every number labeled and defined?" |
| C09 | Error messages: what/why/fix | MIL-STD-1472H | CDP: trigger error states, VLM: "does error explain what, why, and how to fix?" |
| C10 | Destructive actions require confirmation | MIL-STD-1472H | CDP: click delete/reject buttons, verify confirmation dialog |
| C11 | Undo available for significant actions | MIL-STD-1472H | CDP: perform action, check for undo affordance |
| C12 | Audit trail visible: user, time, session | NIST 800-53 AU-2/AU-3 | VLM: crop headers, ask "are user, timestamp, and session ID visible?" |
| C13 | Session timeout warning | NIST 800-53 AC-11 | Check for inactivity timer UI |
| C14 | Tooltips on non-obvious elements | MIL-STD-1472H | CDP: hover all `[data-qid]` elements, check for `title` attribute |
| C15 | Input has feedback (loading/success/error) | MIL-STD-1472H | CDP: submit input, verify visual feedback state change |

## Usage

```bash
# Scan a running URL
./run.sh scan http://localhost:3002/#embry-terminal

# Scan with specific manifest (lists which elements to check)
./run.sh scan http://localhost:3002/#embry-terminal --manifest cots-manifest.yaml

# Generate fix plan from violations
./run.sh scan http://localhost:3002/#embry-terminal --plan

# Check only specific rules
./run.sh scan http://localhost:3002/#embry-terminal --rules C01,C02,C03

# Output as JSON
./run.sh scan http://localhost:3002/#embry-terminal --json
```

## Architecture

```
1. Launch headless Chrome (CDP on port 9222)
2. Navigate to target URL, wait for render
3. For each rule in checklist:
   a. PROGRAMMATIC rules (C01-C03, C05-C06, C14):
      - CDP Runtime.evaluate to measure font sizes, touch targets, contrast
      - Direct pass/fail based on numeric thresholds
   b. VISUAL rules (C04, C07-C09, C12):
      - CDP crop relevant elements via data-qid
      - Process through vlm_image.py (upscale, sharpen)
      - Send to Gemini Flash with adversarial prompt
      - Parse pass/fail from VLM response
   c. INTERACTION rules (C10-C11, C13, C15):
      - CDP click/submit elements
      - Screenshot before/after
      - Check for expected UI state changes
4. Output report: PASS/WARN/FAIL per rule with screenshots
5. Optionally generate /plan YAML of fixes
```

## Manifest Format

```yaml
# cots-manifest.yaml
url: "http://localhost:3002/#embry-terminal"
wait_ms: 8000
setup_steps:
  - evaluate: 'document.querySelector("[data-testid=tab-final-site]")?.click()'
  - wait: 2000

elements:
  - qid: "reasoning-chain-summary"
    label: "Thinking label"
    rules: [C01, C02, C03, C07, C08, C12, C14]

  - qid: "reasoning-chain"
    label: "Reasoning chain"
    expand: 'document.querySelector("[data-qid=reasoning-chain-summary]")?.click()'
    rules: [C01, C03, C04, C07, C08, C09, C14]

  - qid: "input:compose"
    label: "Input field"
    rules: [C01, C02, C05, C15]

  - qid: "input:send"
    label: "Send button"
    rules: [C02, C06]

  - qid: "topbar:agent:select"
    label: "Agent picker"
    rules: [C02, C14]

  - qid: "sidebar:project:*"
    label: "Project list items"
    rules: [C02, C03]

interactions:
  - action: "submit_empty_input"
    steps:
      - evaluate: 'document.querySelector("[data-qid=input:send]")?.click()'
      - wait: 500
    rules: [C09, C15]

  - action: "keyboard_tab_through"
    steps:
      - press: "Tab"
      - repeat: 20
    rules: [C05, C06]
```

## Output

```
╔══════════════════════════════════════════════════════════════╗
║  COTS Compliance Report — Embry Terminal                    ║
║  URL: http://localhost:3002/#embry-terminal                 ║
║  Date: 2026-04-01T20:15:00Z                                ║
╠══════════════════════════════════════════════════════════════╣
║  PASS: 9  WARN: 3  FAIL: 3  TOTAL: 15                     ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  C01 Font sizes ≥ 16px                          FAIL        ║
║    → reasoning-chain-summary: "conf 91%" at 10px            ║
║    → step metadata: duration at 9px                         ║
║    Screenshot: captures/cots/C01-font-violation.png         ║
║                                                              ║
║  C02 Touch targets ≥ 44x44px                    WARN        ║
║    → step-children-toggle: 28x28px (min 44)                 ║
║    Screenshot: captures/cots/C02-touch-violation.png        ║
║                                                              ║
║  C03 Color contrast ≥ 4.5:1                     PASS        ║
║  C04 Color not sole carrier                     PASS        ║
║  C05 Keyboard navigation                        FAIL        ║
║    → 4 elements unreachable via Tab                         ║
║  ...                                                         ║
╚══════════════════════════════════════════════════════════════╝
```

## Fix Plan Generation

When `--plan` is passed, generates a YAML task file:

```yaml
version: 1
kind: orchestrate-plan
metadata:
  title: "COTS Compliance Fixes — Embry Terminal"
  goal: "Fix 3 FAIL + 3 WARN violations from best-practices-cots scan"
  plan_type: code
tasks:
  - id: "1"
    title: "Fix C01: Bump metadata font sizes to ≥ 12px (16px preferred)"
    lane: "0"
    runner: "subagent-service"
    backend: "sonnet"
    executor: "Project agent"
    implementation:
      - "In ReasoningChain.tsx: change all fontSize: 9/10 to minimum 12"
      - "In StepContent: change summary fontSize from 13 to 16"
    definition_of_done:
      command: "./run.sh scan http://localhost:3002/#embry-terminal --rules C01 --json | jq '.C01.status'"
      assertion: "Returns PASS"
```

## Dependencies

| Skill/Tool | Role |
|---|---|
| `common/vlm_image.py` | Crop, upscale, sharpen screenshots for VLM |
| `/scillm` (text-gemini) | VLM visual analysis for subjective rules |
| Chrome + CDP | Headless browser for programmatic measurement |
| `/plan` | Fix plan YAML generation |
