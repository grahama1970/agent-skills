---
name: review-design
description: >
  Multi-provider AI design review of UI screenshots and design tokens for UX audits.
triggers:
  - review design
  - design review
  - UX audit
  - audit this UI
  - review this UI
  - review the design
  - critique this design
  - compare to raycast
  - design comparison
  - visual review
  - UI review
  - check the UX
  - assess the design
  - design feedback
allowed-tools:
  - Bash
  - Python
metadata:
  short-description: Vision-driven UX design review

provides:
  - review-design
composes: [task-monitor, memory, scillm]
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# review-design

Multi-provider AI design review skill. Submits UI screenshots + design tokens to vision-capable LLMs for structured UX audits.

## PERSONA REQUIREMENT (NON-NEGOTIABLE)

**Every review MUST specify `--persona`.** A review without a persona is a failure — it produces generic, unfocused feedback that wastes everyone's time.

The `--persona` flag:
1. Loads the persona's AGENTS.md (identity, domain expertise, review dimensions)
2. Runs `/memory recall` for the persona's scope (prior reviews, QRA corpus, relationships)
3. Injects all context into the system prompt so the LLM reviews AS that persona

```bash
# CORRECT — persona-driven review
./run.sh review --persona brandon-bailey --screenshots ./screenshots/ --tokens ./tokens.json

# WRONG — will fail with validation error
./run.sh review --screenshots ./screenshots/ --tokens ./tokens.json
```

Available personas for design review:
- `brandon-bailey` — CMMC/compliance reviewer (4,017 controls, 77,528 relationships)
- `rob-armstrong` — Formal verification reviewer (Lean4 proof obligations)
- `margaret-chen` — Quality assurance reviewer
- `nico-bailon` — Extraction QA reviewer (PDF fidelity, tables, sections, quarantine triage)

## Triggers

- review design
- design review
- UX audit
- audit this UI
- review this UI
- review the design
- critique this design
- compare to raycast
- design comparison
- visual review
- UI review
- check the UX
- assess the design
- design feedback

## Description

Iterative 3-step design review pipeline inspired by `review-code`:

1. **Audit** - Analyze screenshots against design tokens + reference images, identify gaps
2. **Judge** - Critique the audit findings for accuracy and prioritization
3. **Finalize** - Produce actionable recommendations with specific token/layout changes

Supports multiple vision-capable providers:
- **Claude** (`claude`) - claude-sonnet-4-20250514 (vision)
- **OpenAI** (`openai`) - gpt-4o (vision)
- **Gemini** (`gemini`) - gemini-2.0-flash (vision)
- **Subagent** (`subagent`) - any model via `/subagent-service` (supports image I/O)

## Requirements

**Screenshots are MANDATORY.** This skill will fail if no screenshots are provided. A design review without visual evidence is impossible — it would be pure speculation.

Capture screenshots before running a review:
- `/surf snap` — Browser screenshot via CDP
- `/surf-qml` — QML/Qt app screenshot via AT-SPI
- `flameshot full --path ./screenshots/current.png` — System screenshot

The `--screenshots` directory must contain at least one PNG/JPG image.

## Usage

```bash
# Basic design review (single round) — persona is REQUIRED
./run.sh review --persona brandon-bailey --screenshots ./screenshots/ --tokens ./design-tokens.json

# With reference images (compare to target design)
./run.sh review --persona rob-armstrong --screenshots ./current/ --reference ./raycast/ --tokens ./tokens.json

# Multi-round iterative review (recommended)
./run.sh review --persona brandon-bailey --screenshots ./current/ --reference ./target/ --tokens ./tokens.json --rounds 2

# Specific provider
./run.sh review --persona margaret-chen --provider claude --screenshots ./ui/

# Animation review with burst filmstrip + source code context
./run.sh review --persona rob-armstrong --screenshots ./screenshots/s6-sentinelhud/ \
  --tokens ./tokens/s6-sentinelhud.design-tokens.json \
  --code-context ./src/components/EmbryThinkingIcon.tsx \
  --code-context ./src/styles/distance.css \
  --rounds 2

# Generate review request bundle (for manual submission)
./run.sh bundle --screenshots ./ui/ --tokens ./tokens.json --output review_request.md
```

## Burst Filmstrip Mode

For reviewing animations (particle systems, state transitions, force rings), use
burst capture to generate filmstrip frames that show the animation over time:

```bash
# 1. Capture burst filmstrips (10 frames over 2s per state transition)
python scripts/capture_matrix.py --burst

# 2. Frames saved to docs/screenshots/{surface}/burst/{persona}_{state}_f01..f10.png
#    Regular resting-frame screenshots still captured alongside

# 3. Run review — burst/ subdirectory auto-included
./run.sh review --screenshots ./docs/screenshots/s6-sentinelhud/ \
  --code-context ./src/components/EmbryThinkingIcon.tsx \
  --tokens ./tokens.json
```

The reviewer sees the animation code AND the frame-by-frame filmstrip, enabling
verification of force ring emergence, dash rotation, ripple expansion, and color
transitions that are invisible in single static screenshots.

With Gemini's 1M context window, 50+ screenshots + full source files fit easily.

## Input Format

### Design Tokens (JSON)
```json
{
  "meta": { "name": "...", "description": "..." },
  "colors": { ... },
  "typography": { ... },
  "layout": { ... },
  "animation": { ... },
  "effects": { ... },
  "interactions": { ... }
}
```

### Screenshots
- PNG/JPG files in a directory
- Named descriptively: `full-launcher-empty.png`, `result-list-hover.png`
- Include both current UI and reference/target UI if comparing

## Output Format

### Per-Round Files (in `review_output/`)
```
roundN_step1.md      # Initial audit findings
roundN_step2.md      # Judge critique
roundN_final.md      # Finalized recommendations
roundN_audit.json    # Structured findings (machine-readable)
```

### Audit JSON Structure
```json
{
  "summary": "Overall assessment",
  "findings": [
    {
      "severity": "high|medium|low",
      "category": "color|typography|layout|spacing|animation|interaction",
      "element": "search-bar",
      "issue": "Description of the gap",
      "current": "Current value or behavior",
      "recommended": "Suggested fix",
      "token_change": { "path": "colors.text.primary", "from": "#fff", "to": "#f5f5f5" }
    }
  ],
  "token_changes": [ ... ],
  "praise": [ "Things done well" ]
}
```

## Provider Capabilities

| Provider | Model | Vision | Codebase Access | Default |
|----------|-------|--------|----------------|---------|
| **subagent** | gemini-2.5-pro (via `/subagent-service`) | Yes | **Yes** — Docker mounts full codebase + 237 skills | **DEFAULT** |
| claude | claude-sonnet-4-20250514 | Yes | No — screenshots only | |
| openai | gpt-4o | Yes | No — screenshots only | |
| gemini | gemini-2.0-flash | Yes | No — screenshots only | |

### Why Subagent is Default

The subagent provider routes through `/subagent-service` (Docker container) which has:
- **Full codebase access** — can read React components, design tokens, CSS alongside screenshots
- **All 237 skills mounted** — can cross-reference `/best-practices-react`, `/taxonomy`, etc.
- **Persona agents** — loaded from `.pi/agents/` for persona-driven reviews
- **Memory/embedding services** — connected to host ArangoDB for prior review context

Direct providers (claude/openai/gemini) only see the base64 images + whatever code context
you manually pass via `--code-context`. They can't grep the codebase or check if a design
token is actually used correctly in the implementation. Subagent can.

## Commands

### `review` - Single-round design audit
Basic audit with optional reference comparison.

### `review-full` - Multi-round iterative audit (recommended)
Runs the 3-step pipeline for N rounds, each round refining findings.

### `bundle` - Generate review request
Creates a markdown file with embedded images (base64) for manual submission to any LLM.

### `compare` - Side-by-side comparison
Generates a visual comparison report between current and target design.

### `check` - Verify provider access
Tests that the selected provider has vision capability and valid credentials.

## Example Workflow

```bash
# 1. Capture screenshots of your UI
flameshot full --path ./screenshots/current.png

# 2. Gather reference screenshots (e.g., Raycast)
cp ~/raycast-ref/*.png ./screenshots/reference/

# 3. Create/update design tokens
cat > design-tokens.json << 'EOF'
{ "colors": { ... }, "typography": { ... } }
EOF

# 4. Run iterative design review (PERSONA IS REQUIRED)
./run.sh review \
  --persona brandon-bailey \
  --screenshots ./screenshots/ \
  --reference ./screenshots/reference/ \
  --tokens ./design-tokens.json \
  --rounds 2 \
  --provider claude

# 5. Apply recommendations
# Read review_output/round2_final.md for actionable changes
```

## Integration with review-code

After design review produces token changes, you can:
1. Update your style files (QML, CSS, etc.) based on recommendations
2. Run `review-code` to validate the implementation changes
3. Iterate until both design and code reviews pass

## Allowed Tools

- Bash (for provider CLI invocation)
- Read (for loading tokens and configs)
- WebFetch (for fetching remote design specs)

## Notes

- Screenshots should be captured at 1x scale for consistent analysis
- Include the full UI context (not just cropped elements) for better spatial reasoning
- Reference images help but aren't required. However, screenshots ARE required — the skill will fail without them.
- Large images are automatically resized to fit provider limits

## Common Mistakes

### WRONG: Running a review without specifying --persona
```bash
./run.sh review --screenshots ./screenshots/  # fails validation, generic feedback
```

### RIGHT: Always specify persona for focused, domain-expert review
```bash
./run.sh review --persona brandon-bailey --screenshots ./screenshots/
```

### WRONG: Running review without screenshots (impossible)
```bash
./run.sh review --persona brandon-bailey --tokens ./tokens.json  # no screenshots!
```

### RIGHT: Capture screenshots first, then review
```bash
flameshot full --path ./screenshots/current.png
./run.sh review --persona brandon-bailey --screenshots ./screenshots/
```

### WRONG: Using direct provider (claude/openai) instead of subagent
```bash
./run.sh review --persona brandon-bailey --provider claude --screenshots ./ui/
# Loses codebase access, can't cross-reference components
```

### RIGHT: Use subagent (default) for full codebase + skill access
```bash
./run.sh review --persona brandon-bailey --screenshots ./ui/
# subagent has Docker-mounted codebase, 237 skills, memory access
```
