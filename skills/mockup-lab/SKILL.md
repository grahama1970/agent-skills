---
name: mockup-lab
description: >
  Iterative UI mockup generation via Gemini (multimodal) and Google Stitch.
  Gemini generates mockups from reference screenshots + text specs.
  Stitch SDK pulls/manages designs from Stitch web UI (text-only, no image input).
  /review-design scores quality, /interview collects human decisions.
triggers:
  - mockup
  - create mockup
  - design mockup
  - iterate mockup
  - stitch
  - generate UI
  - design iteration
  - mockup lab
  - ui mockup
  - design exploration
  - explore views
allowed-tools: Bash, Read, Write
read_before_use: stitch_cli.mjs
metadata:
  short-description: "UI mockup generation via Gemini (multimodal) + Stitch (text-only pull)"

provides:
  - mockup-lab
  - design-target
composes:
  - review-design
  - interview
  - memory
  - scillm

taxonomy:
  - design
  - ui
  - visualization
disciplines:
  - ui-design-engineering
  - content-creation
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# mockup-lab

Iterative UI mockup generation. Convergence loop: **generate → review → iterate** until approved.

## Why This Exists

Claude is bad at visual design. This skill delegates mockup generation to Gemini
(multimodal — accepts reference screenshots + text) and keeps Claude focused on
spec writing, code review, and iteration orchestration.

## Design Generation Strategy (2026-03-21)

**Primary: Gemini via /scillm** (multimodal mockup generation)
- Send reference screenshots + spec text → get HTML mockup back
- Can see existing UIs, wireframes, competitive products
- Agent-driven, no quota wall

**Alternative: /subagent-service with Gemini backend**
- Docker container with full codebase + all skills mounted
- Use when mockup needs awareness of existing React components, design tokens, hooks
- More expensive but richer context

**Stitch SDK (demoted to pull-only)**
- SDK accepts text only — no images, no URLs, no HTML seeds
- Useful for: pulling designs human built in Stitch web UI, listing projects
- The Stitch *web UI* is multimodal (paste screenshots, sketch, voice) — human uses it directly
- Do NOT rely on Stitch SDK for generating new designs from visual references

## How to Prompt Stitch (NON-NEGOTIABLE)

Reference: https://discuss.ai.google.dev/t/stitch-prompt-guide/83844

Stitch is a visual designer. Prompt it like a human designer, not a CSS renderer.

**Rules:**
1. **Under 100 words** — long prompts cause Stitch to drop CSS entirely
2. **Reference existing products** — "like GarageBand", "like Suno Studio", "like Figma layers"
3. **State the PURPOSE** — "for selecting reference clips from stems"
4. **State CONSTRAINTS** — "dark theme, 5 tracks, no mixing controls, desktop"
5. **Do NOT specify** hex colors, pixel sizes, border-radius, opacity — Stitch knows the design system from DESIGN.md
6. **Do NOT list anti-patterns** — "do NOT use white" wastes prompt budget
7. **Let Stitch design** — that's its strength, not yours

**Good prompt (47 words):**
> GarageBand-style stem viewer. 5 colored tracks (vocal, bass, drums, keys, guitar) with
> waveforms. Dark theme. Per-track selection handles for picking reference clips. Album art
> + song title at top. Selected clips shown as cards at bottom. Desktop layout.

**Bad prompt (causes CSS dropout):**
> Create a screen with background #141414, cards #1a1a1a, border rgba(255,255,255,0.13),
> 12px radius. Each track should be 60px tall with 3px left border... *(500 more words)*

**Incident:** 2026-03-20 — Agent sent 8 verbose prompts to Stitch for the Music Lab stem viewer.
3 produced unstyled HTML (CSS dropped). The human created the correct design in 1 prompt
by referencing "GarageBand-style" instead of describing every pixel.

## Three Tools, No Gatekeeper (2026-03-21)

| Tool | Who drives it | Multimodal | Best for |
|------|--------------|------------|----------|
| **Gemini API** | Agent | Yes (images + text → HTML) | Reference-driven mockups: "make it look like PromptFoo but with NVIS theme" |
| **Stitch web UI** | Human | Yes (paste screenshots, sketch, voice) | Visual iteration: human pastes reference images, iterates in browser |
| **Stitch SDK** | Agent | No (text-only) | Pull finished designs, manage projects, generate variants from text prompts |

Use whichever fits the moment. None is a dependency or gatekeeper.

### Gemini mockup generation (agent-driven)

When the agent has reference screenshots, send them to Gemini with a short prompt.
Follow the same discipline as Stitch prompts: under 100 words, reference existing
products, state purpose and constraints.

```bash
# Agent sends reference image + spec to Gemini → gets HTML mockup
./run.sh mockup --image reference.png --spec spec.md --output mockup.html
```

### Stitch web UI (human-driven)

The human can paste/upload reference screenshots directly into Stitch's web UI
(it supports multimodal input), iterate visually, then the agent pulls the result:

```bash
# Human iterates in Stitch web UI at https://stitch.withgoogle.com/projects/<id>
# Agent pulls the finished design:
./run.sh pull --project <id> --screen <id> --output captures/
```

### Stitch SDK (text-only, agent-driven)

For text-only generation when no visual reference exists:

```bash
./run.sh generate --spec spec.md
```

### Blockers: be transparent

If any tool fails (quota exhausted, auth broken, bad output), TELL THE HUMAN
IMMEDIATELY in one sentence. Do not silently fall back to a worse approach.

## Prerequisites

```bash
# API key in .env or environment
export STITCH_API_KEY="your-key"

# SDK installed (auto-installed on first run)
npm install @google/stitch-sdk
```

## End-to-End Example (New Project)

```bash
# 1. Write a spec (see local/docs/mockups/binary-explorer-stitch-spec.md for format)
#    Spec = markdown with: what it is, who uses it, real data, layout wireframe,
#    what NOT to do, and 2-3 variation directions.

# 2. Create DESIGN.md with your design system tokens (optional but recommended)
#    See local/docs/mockups/DESIGN.md for NVIS example

# 3. Generate initial mockup from spec
./run.sh generate --spec local/docs/mockups/my-spec.md
# → outputs: projectId, screenId, stitchUrl (open in browser)

# 4. Human reviews in Stitch browser at the URL
# 5. Agent asks for structured feedback:
#    /interview "Which direction should we pursue?" with options from variants

# 6. Iterate based on feedback
./run.sh iterate --project 9890074554556221968 --screen abc123 \
  --feedback "Make the graph larger, add tier badges to nodes"

# 7. Generate all sidebar/nav views BEFORE writing any code
#    First create a views.json with your project's views (see "Views File Format")
./run.sh explore --project 9890074554556221968 --screen abc123 \
  --views views.json --output packages/ux-lab/captures/my-project/views/
# → generates 1 screen per view entry, 3s cooldown between each
# → writes manifest.json listing every view + screenshot path

# 8. Pull the approved base screen HTML
./run.sh pull --project 9890074554556221968 --screen abc123 \
  --output packages/ux-lab/captures/my-project/

# 9. Now build the React component using the screenshots as reference

# 10. Or run the full pipeline:
#     /orchestrate run .pi/skills/mockup-lab/design-to-code.yaml
```

## Full Pipeline: design-to-code

See `design-to-code.yaml` for the step-by-step workflow. It's a checklist, not an
`/orchestrate` file — the agent reads it and executes each step directly.

Each step runs as a **subagent** for context protection. The subagent gets only the
context it needs (spec, screenshots, diff), not the full conversation history.

```
Step 1: Write spec         → subagent reads docs/spec-template.md, writes spec.md
Step 2: Generate           → subagent runs ./run.sh generate
Step 3: Human review       → /interview, ./run.sh iterate (loop)
Step 4: Explore views      → subagent runs ./run.sh explore
Step 5: Pull               → subagent runs ./run.sh pull
Step 6: Code               → subagent reads screenshots, writes React component
Step 7: Review             → subagent runs ./run.sh review, reads diff, fixes code (loop)
Step 8: Ship               → /review-design + human sign-off
```

The self-improvement loop is step 7: Gemini VLM compares the component screenshot
against the Stitch design target. Same model family that designed it also judges the
implementation. The subagent reads the structured diff and fixes code until
match_score >= 90.

## Joining an Existing Project

```bash
# List all projects
./run.sh list
# → shows project IDs + screen counts

# List screens in a project
./run.sh list --project 9890074554556221968
# → shows screen IDs

# Pull a specific screen locally
./run.sh pull --project 9890074554556221968 --screen abc123 \
  --output captures/stitch/

# Iterate on it
./run.sh iterate --project 9890074554556221968 --screen abc123 \
  --feedback "Add a chat panel at the bottom"

# Generate 3 layout variants
./run.sh variants --project 9890074554556221968 --screen abc123 \
  --prompt "Try different graph layouts" --count 3
```

## Commands

| Command | Description |
|---------|-------------|
| `generate` | Create a new Stitch project + screen from a spec markdown file |
| `variants` | Generate N variations (1-5) with creative range (REFINE/EXPLORE/REIMAGINE) |
| `iterate` | Edit a screen with feedback text (from /review-design or human) |
| `pull` | Download screen HTML + screenshot to local captures/ |
| `list` | List projects and screens |
| `explore` | Auto-generate screens from a `--views` JSON file (1 credit/view) |
| `theme` | Extract Tailwind config + design tokens from a project |
| `converge` | Full loop: generate → /review-design → /interview → iterate |
| `review` | Visual diff via Gemini VLM: compare component screenshot vs Stitch design target |

## Self-Improvement Loop: Design → Code → VLM Review

The full pipeline doesn't end at mockup approval. After the React component is built,
Gemini VLM (via `/scillm`) compares the implementation against the Stitch design target.
Same model family as Stitch (Gemini 3 Flash), but with direct image input.

```
1. /mockup-lab generate/iterate → approved Stitch mockup (design target)
2. Build React component in /ux-lab
3. npm run dev → render component with real data
4. /mockup-lab review → pulls design target from Stitch + screenshots component
   → sends both images to Gemini VLM for visual diff
5. VLM returns structured JSON: match_score, differences[], iterate_prompt
6. If match_score < 90: agent fixes code → go to step 3
7. If match_score >= 90: done, implementation matches design
```

```bash
# After component is built and rendering:
./run.sh review --project <id> --screen <design-target-id> \
  --screenshot /tmp/component-screenshot.png

# Output: review.json with match_score, differences, and iterate_prompt
# If iterate needed:
./run.sh iterate --project <id> --screen <id> --feedback "<iterate_prompt>"
```

The `review` command:
1. Pulls the design target screenshot from Stitch
2. Reads the component screenshot from disk
3. Sends both to Gemini VLM (`vlm` alias on scillm localhost:4001)
4. Returns structured diff with specific corrections (px, hex colors, font sizes)
5. Generates an `iterate_prompt` ready to feed back to Stitch

## Rate Limits & Cooldown

Stitch enforces daily generation credits:
- **Free tier**: ~350 generations/month, ~100-150/day
- **Paid tier**: ~150 designs/day, resets midnight Pacific
- After hitting limit: soft cooldown, 429 errors

The skill handles this automatically:
- **3s cooldown** between API calls (configurable via `STITCH_COOLDOWN_MS` env)
- **Exponential backoff** with jitter on RATE_LIMITED errors (4 retries, 5s→60s)
- **`explore` command** spaces out view generation with cooldown between each

Cache results aggressively — `pull` downloads HTML + screenshots locally so you
don't re-fetch from Stitch.

## Workflow: Design Questions → Stitch, Architecture Questions → /interview

| Question type | Route to | Example |
|---------------|----------|---------|
| Visual/layout | Stitch `iterate` | "Should we show source code or raw patterns?" |
| View exploration | Stitch `explore` | "What does each sidebar view look like?" |
| Color/theme | Stitch `iterate` + DESIGN.md | "Apply NVIS MIL-STD-3009 palette" |
| Layout variants | Stitch `variants` | "Try 3 different graph layouts" |
| Architecture | `/interview` human | "New ArangoDB collections or reuse lessons?" |
| Data model | `/interview` human | "Treesitter params, schema fields, or both?" |

## Workflow: Explore All Views Before Building

**NON-NEGOTIABLE**: Before writing ANY component code, run `explore` to generate
every view the design has. This prevents hallucinating layouts that don't exist
in the approved design.

```bash
# 1. Get the base screen (the main/default view)
./run.sh list --project <id>

# 2. Create a views.json for YOUR project's navigation/sidebar views
cat > views.json <<'EOF'
[
  { "name": "dashboard", "prompt": "Show the main dashboard view with pipeline stages..." },
  { "name": "mixer", "prompt": "Show the mixer view with channel strips..." },
  { "name": "settings", "prompt": "Show the settings view with model selection..." }
]
EOF

# 3. Generate all views from the base screen
./run.sh explore --project <id> --screen <base-screen-id> \
  --views views.json --output captures/views/

# 4. Review manifest.json — every view has a screenshot
cat captures/views/manifest.json

# 5. Only THEN start building React components
```

The `explore` command requires a `--views` JSON file — an array of `{ name, prompt }`
objects. Each entry costs 1 Stitch credit. Budget accordingly (paid tier: ~150/day).

See [REFERENCE.md](references/REFERENCE.md) for spec file format, views file format, manifest format, human-in-the-loop handoff, design system files, convergence loop, pipeline position, and Stitch SDK reference.

---

# <Project Name> — Stitch Design Spec

## What This Is
One paragraph: what the tool does, who uses it, what problem it solves.

## The User
Who uses this? What are they trying to accomplish? What's their context?

## Real Data
Actual data the mockup should show — NOT lorem ipsum.
Include counts, names, categories, relationships, sample values.
The more concrete the data, the better the mockup.

## Layout
ASCII wireframe of the main view. Show major regions, panels, nav.

## Design System (optional)
If you have a DESIGN.md or tokens file, summarize key colors/fonts here.
Keep under ~2000 chars — Stitch ignores overly long prompts.

## What NOT To Create
Anti-patterns the designer must avoid. Be specific.

## Variations
2-3 directions for Stitch to explore in variants.
```

All sections are required except "Design System". Agents should read `docs/spec-template.md`
before writing a spec.
