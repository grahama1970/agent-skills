---
name: interface-design-pipeline
description: >
  Executable research-to-interface tournament for new or redesigned product
  surfaces. Uses the existing github-search and brave-search skills to discover
  references, converts selected patterns into competing HTML/CSS mockups, runs
  bounded designer/reviewer repair loops, inventories existing React/Tailwind/
  shadcn/D3 components, builds implementation competitors in disposable
  worktrees, and emits evidence for a final adjudicator plus human promotion
  gate. Use for research-backed interface bakeoffs, Sparta Chat redesigns,
  mockup-to-React tournaments, and self-improving UI implementation loops.
triggers:
  - interface design pipeline
  - research interface examples
  - research mockup implementation bakeoff
  - Sparta chat redesign pipeline
  - mockup to React tournament
  - interface competitors
  - self improvement UI loop
allowed-tools: [Bash, Read, Write]
metadata:
  short-description: Research -> mockup -> implementation interface tournament
  version: "0.1.0"
provides:
  - interface-design-pipeline
  - interface-tournament
composes:
  - memory
  - github-search
  - brave-search
  - create-design
  - create-mockup
  - mockup-lab
  - review-design
  - loop
  - thunderdome
  - scillm
  - ask
  - ux-lab
  - test-interactions
  - best-practices-design
  - best-practices-react
  - best-practices-d3
  - best-practices-chat
  - best-practices-chat-ux
taxonomy:
  - design
  - orchestration
  - ui
  - evaluation
---

# Interface Design Pipeline

This is an executable internal orchestration skill. It does not replace
`create-design` or the canonical `create-mockup` front door. It gives those
workflows a durable tournament node for the sequence:

```text
memory / brief
  -> GitHub + Brave research fan-out
  -> reference adjudication
  -> N HTML/CSS candidates
       -> explorer -> interface-designer -> checks -> interface-reviewer -> repair
  -> mockup adjudication
  -> existing component inventory
  -> N React implementation worktrees
       -> explorer -> interface-designer -> checks -> interface-reviewer -> repair
  -> final adjudication
  -> human promotion gate
```

## Non-negotiable boundaries

- `github-search` and `brave-search` are reused; do not reimplement search.
- Research extracts patterns and provenance. It does not authorize cloning
  commercial product chrome or copying incompatible open-source code.
- HTML/CSS mockups precede production React when page purpose, hierarchy, or
  workflow is changing.
- Every candidate gets the same brief, evidence packet, rubric, state list, and
  attempt budget.
- The reviewer is read-only. A reviewer edit is a blocked run.
- Deterministic failures cannot be averaged away by a high visual score.
- Implementation cannot start until the existing component inventory passes.
- One disposable worktree per implementation competitor; no auto-merge or push.
- Fresh screenshots, interaction results, loop receipts, and component-reuse
  receipts are required before a winner can be named.
- The adjudicator recommends; the human promotes, requests a hybrid, or rejects.

## Commands

```bash
# Validate the manifest
./run.sh validate --manifest examples/sparta-chat.json

# Compile all phase plans and bounded $loop node specifications
./run.sh plan --manifest examples/sparta-chat.json

# Inspect research commands without calling APIs
./run.sh research --run-dir .interface-design/runs/<run-id>

# Execute GitHub + Brave lanes concurrently and create the research packet
./run.sh research --run-dir .interface-design/runs/<run-id> --execute --jobs 4

# Read durable status
./run.sh status --run-dir .interface-design/runs/<run-id>

# Record a validated subagent review receipt
./run.sh record-review \
  --run-dir .interface-design/runs/<run-id> \
  --phase reference_adjudication \
  --receipt /path/to/review.json
```

The plan command writes exact next commands and stable node JSON. The project
agent owns scheduling, worktree creation, screenshot capture, reviewer dispatch,
and promotion. The generated `$loop` nodes own each bounded candidate repair
transaction.

## Required artifacts

```text
.interface-design/runs/<run-id>/
  manifest.snapshot.json
  brief.md
  status.json
  events.jsonl
  pipeline-receipt.json
  commands.json
  phases/
    01-research/
      plan.json
      raw/<lane>/request.json
      raw/<lane>/stdout.txt
      raw/<lane>/stderr.txt
      raw/<lane>/receipt.json
      references.normalized.json
      research-packet.md
    02-reference-adjudication/
      agent-task.json
      reference-selection.json
    03-mockup-tournament/
      plan.json
      nodes/*.json
      candidates/<id>/index.html
      candidates/<id>/rationale.md
      adjudication.json
    04-component-inventory/
      agent-task.json
      component-inventory.json
    05-implementation-tournament/
      plan.json
      node-templates/*.json
      receipts/
      screenshots/
      interaction-results/
    06-final-adjudication/
      agent-task.json
      adjudication.json
    07-human-promotion/
      gate.json
```

## Named subagents

The pipeline loads role contracts from top-level `agents/` through
`scripts/interface_loop_agent.py`:

| Agent | Capability | Mutability |
|---|---|---|
| `interface-researcher` | Search synthesis, provenance, pattern extraction, component inventory | read-only |
| `interface-designer` | HTML/CSS candidates and React implementation competitors | scoped writes |
| `interface-reviewer` | UX, screenshot, accessibility, interaction, and implementation review | read-only |
| `interface-adjudicator` | Cross-candidate scoring, winner/hybrid recommendation, missing-evidence gate | read-only |

Do not silently substitute a generic coding agent for a named role. If a role
cannot be dispatched, preserve the task artifact and mark the phase `BLOCKED`.

## Manifest contract

Start from `examples/sparta-chat.json`. The manifest must include:

- a brief and surface definition;
- at least one GitHub query and one Brave query;
- at least two mockup competitors and two implementation competitors;
- the same hard constraints and required states for every candidate;
- target repository, target surface, existing component roots, and stack;
- allowed/required changed globs plus deterministic checks;
- a mandatory human promotion gate.

See `references/pipeline-contract.md` for phase receipts, scoring, and stop rules.

## Sparta Chat defaults

For Sparta Chat, load `best-practices-chat` and `best-practices-chat-ux` in every
candidate lane. Preserve the answer-first message order, compact evidence and
artifact receipts, EvidenceWorkspace/ArtifactPanel ownership, stable qids,
distance modes, and the anti-dashboard-theater gate. The example manifest and
brief encode those defaults.

## Stop rules

Stop with `BLOCKED` when either required research source has no successful lane,
the brief is missing, a named agent contract is unavailable, a reviewer edits
files, component inventory is absent, required checks time out, screenshots or
interaction evidence are missing, changed files escape scope, or promotion would
require an unapproved merge/push.

Stop with `NEEDS_CHANGES` when evidence exists but no candidate clears the hard
gates and threshold within its bounded attempt budget. Never continue an
unbounded visual-repair loop.
