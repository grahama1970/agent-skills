---
name: create-mockup
description: >
  Canonical front door for design creation and redesign. Routes new mockups,
  multi-model bakeoffs, design improvement, and ship-stage verification through
  mockup-lab, ask, review-design, create-image, ux-lab, best-practices-react, and
  test-interactions instead of making users choose among fragmented entrypoints.
triggers:
  - create mockup
  - new mockup
  - improve design
  - redesign ui
  - design bakeoff
  - mockup bakeoff
  - compare mockups
  - multiple model mockups
  - ship mockup
  - html css mockup
  - make mockup
allowed-tools: Bash, Read, Write
metadata:
  short-description: Canonical design front door for new, improve, and ship flows
provides:
  - create-mockup
  - design-front-door
composes:
  - mockup-lab
  - ask
  - review-design
  - create-image
  - ux-lab
  - best-practices-react
  - test-interactions
  - create-design-board
  - create-styleguide
taxonomy:
  - design
  - ui
  - orchestration
disciplines:
  - ui-design-engineering
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /create-mockup

Canonical front door for design work in `pi-mono`.

This skill exists to remove entrypoint drift. The user should not have to choose
between `/mockup-lab`, `/create-react-designs`, `/prototype-react-iterate`,
`/create-design-board`, and `/create-styleguide` just to start designing an
interface.

## The Contract

- `/create-mockup new` is the start point for new designs
- `/create-mockup bakeoff` is the start point when design judgment is uncertain
  and the user wants N independent model candidates before selecting a direction
- `/create-mockup improve` is the start point for redesigning an existing UI
- `/create-mockup ship` is the start point for moving an approved mockup into a
  coded and verified interface
- `/review-design` is the critique stage
- `/ask` is the concurrent model-fanout stage for bakeoffs; it should use
  `$scillm` batch/as-completed execution internally where possible, generate
  independent candidates, and expose runtime/SSE progress telemetry
- `/test-interactions` is the deterministic ship-stage verification gate for
  live rendered interfaces

## Decision Rule

- If the user wants a mockup or redesign, use `/create-mockup`
- If the user wants multiple models to propose interface directions, use
  `/create-mockup bakeoff`
- If the user wants critique only, use `/review-design`
- If the user wants assets or references only, use `/create-image`
- If the user wants packaging/governance only, use `/create-design-board` or
  `/create-styleguide`

## Non-Negotiable Routing

### `new`

Use for a new UI direction from a brief, screenshots, or references.

- HTML/CSS UI mockups go through `/mockup-lab`
- Reference art, icons, backgrounds, and supporting visual assets go through
  `/create-image`
- Do not use image generation as the source of truth for product UI layout

### `bakeoff`

Use when a single-agent design pass is likely to produce tunnel vision or when
the user explicitly wants multiple model candidates.

- `/create-mockup bakeoff` owns the workflow.
- `/ask` owns concurrent model fanout and progress telemetry. For provider
  lanes that can use `$scillm`, this should be a bounded `$scillm` batch or
  `as_completed` fanout inside `$ask`, not a serial loop of oracle calls.
- `/review-design` owns screenshot-based judging after candidates render.
- The current/original design may be included as a baseline candidate, but it
  must be labelled `baseline` or `failed-baseline` unless the user explicitly
  says it can compete.
- Each model receives the same brief, screenshots, constraints, non-goals,
  scoring rubric, and baseline failure analysis.
- Reference screenshots may be included to communicate qualities such as
  spaciousness, calm density, typography, input affordances, and navigation
  restraint. Treat them as quality references, not templates to clone. Do not
  copy Gemini, Claude, ChatGPT, Raycast, Linear, or any other product chrome
  unless the brief explicitly asks for a clone.
- A bakeoff must explicitly reject another legacy dashboard/chat hybrid. If the
  user says "not a dashboard", candidates that lead with dashboard chrome,
  permanent metric panels, persistent context wells, boxed grid walls, or generic
  AI-ops SaaS layout patterns fail the hard constraints before visual scoring.
- Candidate generation must run concurrently, not serially, when the requested
  models are independent.
- Long-running bakeoffs must use `$ask` runtime artifacts and `$scillm`
  SSE-backed progress where available. Do not launch opaque background jobs
  without status files, event logs, and a bounded watcher.
- For any run expected to exceed five minutes, create watchdog/status monitoring
  before launching the model calls. Monitor per-candidate state, stalled runs,
  empty outputs, and failed artifact extraction.

Default model lanes:

| Lane | Purpose |
| --- | --- |
| `claude` | visual hierarchy, editorial/compliance tone, restraint |
| `openai` | implementation-realistic product UI and interaction details |
| `gemini` | alternate visual direction and modern interaction patterns |
| `opencode-kimi` | information architecture, state mechanics, structural critique |

Required bakeoff outputs:

- `baseline/` when an original design is supplied, including screenshot and
  `failure-analysis.md`
- `references/` when design references are supplied, including `takeaways.md`
  that extracts reusable qualities without copying product-specific chrome
- `candidates/<model>/index.html`
- `candidates/<model>/rationale.md`
- `screenshots/<model>.png`
- `reviews/<model>/` from `/review-design`
- `scores.json`
- `winner.md`
- `hybrid-plan.md` when no single candidate should win
- `index.html` comparison board with tabs for baseline, candidates, matrix, and
  winner/hybrid rationale

### `improve`

Use for redesigning an existing interface.

- Start with `/review-design` to establish what is wrong
- Use `/mockup-lab` to iterate the HTML/CSS mockup
- Re-run `/review-design` after the redesign pass

### `ship`

Use once the direction is approved and the interface needs to become
implementation-ready.

- `/ux-lab` is the implementation workbench
- `/best-practices-react` is the implementation hardening layer
- `/test-interactions` is required for live rendered interfaces
- `/review-design` runs again at the end for visual drift

## Commands

```bash
# New mockup from brief + references
./run.sh new --brief "PromptFoo-style eval dashboard" --screenshots ref.png --output out/

# New text-only layout direction
./run.sh new html --spec spec.md

# Multi-model mockup bakeoff from a brief and current baseline
./run.sh bakeoff \
  --brief SPARTA_CHAT_BRIEF.md \
  --models claude,openai,gemini,opencode-kimi \
  --baseline-url http://127.0.0.1:4319/ \
  --persona brandon-bailey \
  --constraints cots,nvis,embry-style,not-dashboard \
  --output ./design-bakeoff/sparta-chat

# Natural chat equivalent:
# "Can you $create-mockup bakeoff with 5 models and pick the winner?"
# The project agent should translate that into this command shape:
./run.sh bakeoff \
  --brief BRIEF.md \
  --models claude,openai,gemini,deepseek,opencode-kimi \
  --count 5 \
  --persona brandon-bailey \
  --constraints cots,nvis,embry-style,not-dashboard \
  --output ./design-bakeoff/<surface-name>

# Generate a supporting asset or reference image
./run.sh new assets "abstract nebula background" --output nebula.png

# Improve an existing design: critique first
./run.sh improve review --persona nico-bailon review --input screenshot.png

# Improve an existing design: iterate an existing mockup-lab project
./run.sh improve iterate --project 123 --screen abc --feedback "Reduce chrome, increase information density"

# Ship stage: work in the implementation canvas
./run.sh ship ux start

# Ship stage: deterministic live-DOM verification
./run.sh ship test full --url "http://localhost:3000" --persona margaret-chen --manifest manifest.json

# Print the canonical routing matrix
./run.sh route
```

## Stage Map

| Mode | Primary route | Supporting routes | Output |
| --- | --- | --- | --- |
| `new` | `/mockup-lab` | `/create-image`, `/review-design` | HTML/CSS mockup plus optional assets |
| `bakeoff` | `/ask` concurrent model fanout | `/review-design`, `/mockup-lab`, `/create-design-board` | tabbed comparison board with baseline, N candidates, scores, and winner/hybrid plan |
| `improve` | `/review-design` then `/mockup-lab` | `/review-design` again | reviewed redesign direction |
| `ship` | `/ux-lab` | `/best-practices-react`, `/test-interactions`, `/review-design` | coded UI with deterministic verification |

## Bakeoff Orchestration Rules

Use this sequence for `/create-mockup bakeoff`:

1. Capture or import baseline screenshots, including collapsed/expanded states
   for navigation-heavy surfaces.
2. Capture or import reference screenshots when useful, then write
   `references/takeaways.md` describing what to learn from them and what not to
   copy.
3. Write a single brief that includes product context, target user, constraints,
   non-goals, and a scoring rubric.
   Include explicit anti-goals such as "do not create another legacy clunky
   chat-dashboard hybrid" when the current design failed that way.
4. If a current design exists, write `baseline/failure-analysis.md` that names
   the exact defects the new candidates must avoid.
5. Launch one model lane per model concurrently with stable artifact IDs:
   `<project>-<surface>-<model>-candidate`.
   If `$ask` supports a single batch request for the selected lanes, prefer that
   batch interface as long as it preserves per-model artifact IDs, progress, and
   failure isolation.
6. Require each model to return static HTML/CSS plus rationale, not only prose.
7. Track every `$ask` run using status artifacts and `$scillm` SSE-backed
   progress where available. Use `./run.sh status --run <ask-id> --watch` or the
   served status monitor instead of blind waiting.
8. Reject candidates that omit hard constraints, produce a dashboard when the
   non-goal says "not a dashboard", recreate a legacy clunky chat-dashboard
   hybrid, or fail to include required interaction states.
9. Render every accepted candidate, capture screenshots, and run
   `/review-design` with the same persona and rubric.
10. Produce a comparison board. The board must clearly mark `winner` or `hybrid`
   and explain why rejected candidates lost.

The bakeoff is a creation workflow, not a review-only workflow. Do not put this
responsibility inside `/review-design`; use `/review-design` only after the
candidates are rendered.

### `$ask` / `$scillm` Boundary

`/create-mockup bakeoff` must not call provider APIs directly. It hands the
candidate-generation contract to `$ask`. `$ask` decides whether to use:

- a bounded `$scillm` batch/as-completed fanout for independent text-only
  candidate generation,
- `$scillm` streaming calls with SSE heartbeats for long single-model lanes, or
- subagent-backed oracle runs for lanes that require codebase access.

Do not implement bakeoff as:

```bash
for model in "${models[@]}"; do ask "$prompt" --oracle --model "$model"; done
```

That serializes design exploration, hides liveness, and loses failure isolation.
The correct contract is concurrent fanout with stable item IDs, status artifacts,
SSE/progress events where available, and per-candidate output directories.

The shared `./run.sh bakeoff` command now provides a concrete implementation of
that contract for text-to-HTML candidates. It writes:

```text
<output>/
  candidates/<model>/index.html
  candidates/<model>/rationale.md
  candidates/<model>/response.md
  run-state/<model>/status.json
  run-state/<model>/events.jsonl
  scores.json
  winner.md
  index.html
```

The scoring pass is a deterministic completeness gate, not a substitute for
human or persona design review. Use `/review-design` on the rendered winner
before shipping.

## Imported Rules

Read `references/make-interfaces-feel-better.md` before writing prompts for a
high-polish design pass. It captures the imported design-engineering rules that
belong in creation-time mockup work.

Use those rules to improve:

- concentric radii
- optical alignment
- typography rhythm
- tabular numbers where numeric scanning matters
- motion discipline
- touch target clarity

## When Not To Use This Skill

- Do not use `/create-mockup` if the user only wants a design review. Use
  `/review-design`.
- Do not use `/create-mockup` if the user only wants a bitmap image or art
  asset. Use `/create-image`.
- Do not use `/create-mockup` if the task is already in pure implementation and
  only needs a code fix. Use the implementation skill directly.

## Packaging and Governance

Packaging is downstream:

- `/create-design-board` for comparison boards and round tracking
- `/create-styleguide` for token callouts, drift tracking, and visual debt

These are not front-door creation skills.

## Output Expectations

At minimum, the agent should leave the user with:

- one clear route selection
- the next concrete command to run
- a clear distinction between mockup creation, critique, implementation, and
  verification
- for bakeoffs: candidate artifact paths, status artifact paths, screenshot
  paths, score matrix, and clear winner or hybrid rationale

Do not blend all stages together. Route to the right stage.
