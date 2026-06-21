---
name: interface-design
description: >
  Research-backed interface design and implementation tournament. Searches GitHub
  and Brave for source-receipted interface precedents, ranks reusable patterns,
  creates static HTML/CSS candidates, runs screenshot-driven reviewer repair loops,
  inventories existing React/Tailwind/shadcn/D3 components, and builds isolated
  implementation competitors with deterministic checks before a human approval gate.
triggers:
  - interface design pipeline
  - research interface patterns
  - search github for interfaces
  - search brave for interfaces
  - mockup tournament
  - html css mockup bakeoff
  - react implementation bakeoff
  - sparta chat redesign
allowed-tools: [Bash, Read, Write]
metadata:
  short-description: Evidence-backed mockup and React implementation tournament
  version: "0.1.0"
provides:
  - interface-design-pipeline
  - reference-research
  - mockup-tournament
  - implementation-tournament
composes:
  - memory
  - github-search
  - brave-search
  - create-mockup
  - review-design
  - surf
  - scillm
  - loop
  - ux-lab
  - best-practices-design
  - best-practices-chat-ux
  - best-practices-react
  - best-practices-d3
  - test-interactions
  - task-monitor
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - design
  - ui
  - research
  - orchestration
---

# Interface Design

Use `/interface-design` when the task needs the whole path from external precedent
research through static mockups and production implementation competitors. It is an
outer project DAG, not another all-purpose coding loop.

## Core contract

```text
brief + prior project evidence
  -> GitHub search || Brave Search
  -> normalized, license-aware reference shortlist
  -> independent HTML/CSS mockup candidates
  -> render every candidate at fixed viewports
  -> screenshot reviewer -> bounded repair rounds
  -> selected static direction or explicit hybrid plan
  -> inventory existing React/Tailwind/shadcn/D3 components
  -> isolated implementation competitors
  -> $loop deterministic code transaction per competitor
  -> $test-interactions + fresh screenshots + $review-design
  -> implementation selection
  -> human approval / merge gate
```

The project agent owns this DAG. `$loop` owns one bounded artifact transaction. The
reviewer is read-only. The human owns unresolved taste, product intent, and final
promotion.

## Why this composes existing skills

- `hum` supplies the evidence-first discovery, comparison-board, receipt, and human
  gate pattern.
- `persona-dream` supplies explicit staged artifacts and fail-closed planning even
  when a downstream renderer is unavailable.
- `scillm` supplies concurrent independent worker lanes with stable IDs and progress
  receipts.
- `loop` supplies explorer → coder → deterministic checks → code-reviewer → repair
  for exactly one scoped implementation artifact.
- `create-mockup` remains the static candidate generator.
- `review-design` remains the screenshot-based design judge; it must not be replaced
  by token counting, DOM text, or HTML completeness heuristics.

## Runtime

Initialize a run:

```bash
skills/interface-design/run.sh init \
  --brief skills/interface-design/examples/SPARTA_CHAT_BRIEF.md \
  --surface sparta-chat \
  --target-repo /path/to/sparta \
  --output /path/to/design-runs/sparta-chat \
  --persona margaret-chen
```

Inspect and update the durable DAG:

```bash
skills/interface-design/run.sh status --run /path/to/design-runs/sparta-chat

skills/interface-design/run.sh record \
  --run /path/to/design-runs/sparta-chat \
  --node research.github \
  --state PASS \
  --artifact research/github-results.json

skills/interface-design/run.sh validate --run /path/to/design-runs/sparta-chat
```

The controller is intentionally provider-free. It creates the run contract and
records truth; project agents and composed skills execute the nodes.

## Required run layout

```text
run/
  README.md
  request.json
  pipeline.json
  brief/design-brief.md
  research/
    queries.json
    raw/github/
    raw/brave/
    reference-candidates.json
    reference-shortlist.json
    reference-rubric.json
  mockups/
    lanes.json
    candidates/<lane>/
    screenshots/<lane>/<viewport>.png
    reviews/<lane>/review_result.json
    repair-rounds/<lane>/<round>/
    review-rubric.json
    selection.json
  components/inventory.json
  implementation/
    lanes.json
    candidates/<lane>/
    loop-receipts/<lane>/final-receipt.json
    screenshots/<lane>/<state>-<viewport>.png
    reviews/<lane>/review_result.json
    review-rubric.json
  final/decision.json
  status/status.jsonl
```

## Phase 1 — research

Run `github-search` and `brave-search` concurrently. Do not use one as a fallback for
the other: GitHub is strongest for implementation evidence; Brave is strongest for
broader product, documentation, and design precedent discovery.

Preserve raw results and normalize every candidate to:

```json
{
  "id": "stable-id",
  "source": "github|brave",
  "title": "...",
  "url": "...",
  "repository": null,
  "license": null,
  "screenshots": [],
  "patterns": [],
  "implementation_evidence": [],
  "accessibility_evidence": [],
  "risks": [],
  "scores": {},
  "selected": false
}
```

Shortlist 6–12 references. Extract reusable qualities and interaction patterns. Do
not clone branded product chrome. Block references whose license/provenance cannot be
established when code or assets would be reused.

## Phase 2 — static mockup tournament

1. Give every designer lane the same brief, shortlist, constraints, data contract,
   states, viewports, and rubric.
2. Require one self-contained `index.html` and a rationale from every lane.
3. Reject incomplete HTML and missing states deterministically.
4. Render accepted candidates at every configured viewport with `surf`.
5. Run `review-design` against the fresh screenshots with the same persona and rubric.
6. Repair only the top candidates, for at most the configured number of outer-DAG
   rounds. Feed the reviewer artifact to the builder; do not summarize away findings.
7. Select one winner or write an explicit hybrid plan. A deterministic completeness
   score may reject a candidate, but it may not choose the visual winner.

The reviewer must be read-only and return `PASS`, `NEEDS_CHANGES`, `BLOCKED`, or
`INSUFFICIENT_EVIDENCE`, plus screenshot evidence and concrete repair instructions.

## Phase 3 — component inventory

After selecting the static direction, scan the target repository before coding.
Inventory:

- React routes and component boundaries
- Tailwind tokens and theme primitives
- shadcn registry/components and local wrappers
- D3/SVG visualizations and shared scales/layout utilities
- storybook/examples and test fixtures
- build, typecheck, lint, unit, E2E, and interaction commands
- components that map directly to selected mockup elements
- genuine gaps requiring a new dependency or component

No implementation lane may ignore this inventory without a written reason.

## Phase 4 — implementation tournament

Each competitor uses an isolated worktree and the same accepted design contract.
Vary implementation strategy, not requirements. The default lanes are:

- `reuse-first`
- `composition-first`
- `accessibility-first`

For each lane:

1. Compile one scoped `$loop` node with allowed/required changed globs and deterministic
   checks.
2. Run explorer → coder → checks → code-reviewer → bounded repair.
3. Validate `final-receipt.json`; process exit alone is not success.
4. For a passing code loop, run `$test-interactions` over the required user flows.
5. Capture fresh screenshots for all required states and viewports.
6. Run `$review-design` for visual fidelity and interaction evidence.
7. If design review returns `NEEDS_CHANGES`, start a new bounded `$loop` node with the
   exact reviewer artifact. Do not let the visual reviewer edit code.

Only competitors passing deterministic gates can enter final visual comparison.

## Selection and stop rules

- Deterministic failures dominate reviewer preference.
- The static winner is provisional until screenshot review.
- The implementation winner is provisional until checks, interaction evidence, and
  screenshot review pass.
- Stop `BLOCKED` for missing credentials, target repository, renderer, test harness,
  or required backend/data contract.
- Stop `NEEDS_CHANGES` when repair budgets are exhausted.
- Never auto-merge, auto-push, or claim human approval.
- Preserve every rejected candidate and the reason it lost.

## SPARTA Chat defaults

For SPARTA-style chat, load `best-practices-chat-ux` and enforce:

- chat is the command surface;
- run/evidence/receipt/artifact objects are typed UI, not prose bubbles;
- full detail belongs in an inspector or drawer;
- durable actions use explicit controls;
- running and blocked states are visible without opening logs;
- no dashboard theater, fake metrics, or private chain-of-thought UI.
