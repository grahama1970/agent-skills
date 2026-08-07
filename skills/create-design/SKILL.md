---
name: create-design
description: >
  Start and manage a research-backed UX/design collaboration loop from a natural
  language design request to brief, references, mockups, structured human review,
  ux-lab implementation, screenshot/CDP proof, reviewer acceptance, and memory
  learning. Use when the human asks to create, redesign, research, review, or
  implement a UX surface; when a design task needs memory, dogpile, ask/scillm
  collaborators, interview HTML review, best-practices-* routing, mockup-first
  workflow, or ux-lab handoff.
metadata:
  short-description: Research-backed UX collaboration loop
provides:
  - design-collaboration-loop
  - ux-brief-generation
  - mockup-review-workflow
composes:
  - best-practices-design
  - memory
  - dogpile
  - ask
  - ux-lab
complies:
  - best-practices-skills
  - best-practices-design
disciplines:
  - ui-design-engineering
  - human-collaboration
---

# Create Design

Use this skill to begin a normal project-agent/human collaboration loop with
additional collaborators and evidence gates. The project agent remains the
coordinator and implementation owner. Human judgment remains authoritative for
product intent, taste, workflow priority, and unresolved ambiguity.

## Runtime Entry Point

Start a design session with:

```bash
skills/create-design/run.sh "redesign PDF Lab labeling UX"
```

Dry-run artifact generation:

```bash
skills/create-design/run.sh --dry-run "redesign PDF Lab labeling UX"
```

The runtime creates `.create-design/runs/<timestamp>-<slug>/` containing:

- `request.json` — normalized request and mode.
- `best-practices-routing.json` — applicable skill routing.
- `collaboration-plan.json` — ordered collaborator loop and evidence gates.

The runtime starts the session artifact trail; it does not replace the project
agent, `plan-iterate`, reviewers, or deterministic validation.

## Collaboration Model

Treat the process as:

```text
project agent ↔ human
project agent ↔ memory ↔ dogpile ↔ ask/scillm ↔ interview ↔ ux-lab
```

Role boundaries:

- **Project agent**: owns plan state, code edits, artifacts, validation, and handoff.
- **Human**: owns product intent, acceptance tradeoffs, and subjective design judgment.
- **Memory**: recalls prior lessons before work and stores final decisions after work.
- **Dogpile**: discovers fresh external references when needed.
- **Ask/scillm**: provide designer, researcher, VLM, and reviewer collaborators.
- **Interview**: gives the human a larger HTML/TUI review surface for images and structured choices.
- **Ux-lab**: implements approved design direction in the React workbench; it is not the design authority.

## Required Loop

1. Run `memory recall` for prior UX lessons, accepted/rejected patterns, personas, and related screenshots.
2. Apply `best-practices-design` to classify the surface and select applicable best-practices skills.
3. Use `dogpile` only when fresh external references, competitor examples, or current design precedents are needed.
4. Use `ask` or `scillm` for interactive designer/researcher/reviewer collaborators.
5. Create a design brief and, when needed, disposable mockups before production React.
6. Launch `interview --mode html` when the human needs image comparison, mockup review, or multi-question feedback.
7. Implement in `ux-lab` only after the design direction is sufficiently accepted.
8. Verify production UI with fresh browser screenshots/CDP and applicable deterministic checks.
9. Run `review-design` or an ask/scillm reviewer gate over replayable artifacts.
10. Store accepted decisions, rejected alternatives, reviewer verdicts, and artifact paths back to `memory`.

## Best-Practices Routing

Always route design work through `best-practices-design`, then load applicable
specialized skills:

| Condition | Skills |
| --- | --- |
| Product UX, workflow, page purpose, IA | `best-practices-design` |
| Frozen screenshot/mockup/external design implementation | `best-practices-codex-design` |
| React component or route implementation | `best-practices-react` |
| Visual polish, typography, motion, hit areas | `make-interfaces-feel-better` |
| D3/SVG charts, graphs, data visualizations | `best-practices-d3` |
| Architecture maps, workflow visuals, proof sheets, infographics | `best-practices-infographic` |
| Skill/workflow contract design | `best-practices-skills` |

If no specialized skill applies, record the non-applicability rationale in the
design brief.

## Interview Auto-Launch Policy

Use `interview` instead of plain chat when:

- multiple mockups or screenshots must be compared;
- the human needs to inspect images;
- the question has more than one independent decision;
- user feedback needs structured options plus free-form override;
- the agent is tempted to infer taste or workflow judgment;
- reviewer output conflicts with human-visible artifacts.

Ask directly in chat only for small binary choices or short clarifications.

## Plan-Iterate Integration

Use `plan-iterate` when the design work must produce durable files, code,
runtime behavior, or acceptance evidence. A design phase should record:

- compact skill context with all collaborators and role boundaries;
- implementation, validation, and review plans for each round;
- mockup/image artifacts and interview responses when applicable;
- screenshot/CDP artifacts for production UI;
- reviewer receipts and deterministic validation logs;
- memory keys or progress-context mirrors for repeated reviews.

Do not mark a design phase accepted from model prose or human chat alone. The
controller needs deterministic artifacts appropriate to the surface.

## Failure Rules

Stop solo iteration and escalate when:

- the same visual/design blocker survives two focused loops;
- the human disproves an agent's design-quality claim with a screenshot or counterexample;
- a dashboard-theater concern remains unresolved;
- real data/artifact sources are missing for a production route;
- reviewers disagree on a material product or visual issue.

Escalation means using `dogpile`, `ask`, `scillm`, or `interview` with the
replayable artifacts, not continuing unbounded local patching.

## Final Handoff Requirements

For a finished design workflow, report only what is backed by artifacts:

- design request/session path;
- memory recall and learn artifacts or explicit skip reason;
- dogpile report path or not-applicable rationale;
- mockup paths and interview response path if used;
- ux-lab files changed, manifest updates, and validation commands;
- screenshot/CDP paths and reviewer verdicts;
- unresolved caveats.

If any required proof is missing, mark the result `pending` or `blocked`, not
complete.
