---
name: best-practices-design
description: >
  Product UX and design-practice guardrails for classifying design work,
  selecting applicable best-practices-* skills, preventing dashboard theater,
  defining mockup-first acceptance criteria, and deciding when to involve
  memory, dogpile, ask/scillm reviewers, interview, ux-lab, review-design, D3,
  React, infographic, or polish-specific skills. Use before creating,
  reviewing, accepting, or implementing UX direction, mockups, workflow
  surfaces, visual explanations, dashboards, or research-backed design changes.
metadata:
  short-description: Product UX and design-routing guardrails
---

# Best Practices Design

Use this skill before UX direction, mockups, visual workflows, dashboard repairs,
review surfaces, or production UI implementation. It decides what kind of design
work is happening and which other skills must be loaded before the agent acts.

## Core Rule

Classify the surface before designing or coding.

Do not treat all UI work as the same task. Separate product design, implementation
fidelity, React code quality, visual polish, data visualization, and infographic
truth-mapping. Load the applicable skill contracts before making claims,
creating mockups, editing React, or accepting reviewer output.

## Surface Classification

Use the first matching surface types:

| Surface | Required skills |
| --- | --- |
| Product workflow, IA, page purpose, primary user job | `best-practices-design` |
| Frozen mockup, external screenshot, Gemini/WebGPT/human design implementation | `best-practices-codex-design` |
| React component, route, action, state, accessibility, component API | `best-practices-react` |
| Motion, radius, typography, hit areas, hover/press states, polish | `make-interfaces-feel-better` |
| D3, SVG chart, graph, force layout, data visualization | `best-practices-d3` |
| Architecture map, workflow visual, state proof sheet, system infographic | `best-practices-infographic` |
| Skill or workflow contract design | `best-practices-skills` |
| Security, compliance, extraction, or domain-specific surface | relevant domain `best-practices-*` skill |

If no specialized best-practices skill applies, state why in the design brief.

## Design Brief Contract

Before mockup or implementation, write a compact brief with:

1. **User job** — one sentence naming what the user is trying to decide or do.
2. **Primary object** — the thing the page or artifact is about.
3. **Primary decision** — the decision/action the surface must support.
4. **Secondary/debug material** — supporting information that must not dominate.
5. **Source of truth** — real data, artifact, screenshot, human decision, or explicit mock/demo status.
6. **Applicable best-practices skills** — selected from the routing table.
7. **Acceptance criteria** — screenshot-visible or artifact-verifiable criteria.
8. **Rejection criteria** — conditions that make the design fail.

## Anti-Dashboard-Theater Gate

Reject or redesign surfaces that show operational truth without a real source.

Forbidden without source-backed data:

- fake health/status/KPI strips;
- arbitrary progress bars or coverage percentages;
- RUNNING/PASS/healthy counters from static data;
- generic queue/activity panels that do not answer the user job;
- placeholder action buttons that imply real backend behavior.

If the authoritative backend, artifact, endpoint, or data contract is missing,
the UI must expose that blocker instead of inventing values.

## Mockup-First Rule

Use mockups before production React when:

- the page purpose, IA, or primary workflow is changing;
- the human calls the existing UI confusing, performative, cluttered, or dashboard theater;
- prior screenshots disproved the agent's design claim;
- multiple layout directions are plausible.

Mockups may use representative/static data only while they are clearly design
artifacts. Production routes must use real artifacts/endpoints or fail closed.

## Human And Reviewer Routing

Use collaborators deliberately:

- Use `memory` first to recall prior UX lessons, accepted/rejected decisions, personas, and screenshots.
- Use `dogpile` when current external precedents, references, or design examples are needed.
- Use `ask` for interactive designer/researcher/reviewer subagents or WebGPT review lanes.
- Use `scillm` for bounded model/VLM critique, comparison, or reviewer aggregation.
- Use `interview` when the human needs an HTML/TUI review surface with images, multiple choices, or structured feedback.
- Use `ux-lab` only after design direction is accepted enough to implement in the React workbench.
- Use `review-design`, `test-interactions`, and browser screenshots/CDP for final visual acceptance.

Ask the human directly in chat only for small binary or short clarifying choices.
Use `interview --mode html` for mockup comparison, screenshot review, image input,
or multi-part design decisions.

## Acceptance Criteria Rules

Acceptance criteria must be observable. Prefer:

- screenshot-visible layout criteria;
- exact artifact paths and data-source contracts;
- reviewer verdicts tied to replayable screenshots or bundles;
- browser/CDP metrics for production UI;
- source-map and truth-label checks for infographics;
- D3 encoding and accessibility checks for visualizations.

Do not accept a design from prose, vibes, DOM existence, or a model's unsupported
summary. Reviewer output is a receipt; deterministic artifacts decide whether
the work is admissible.

## Output Format

When using this skill, produce:

```markdown
## Design Classification
- Surface:
- User job:
- Primary object:
- Primary decision:
- Applicable skills:

## Acceptance Gate
- Must prove:
- Must reject if:
- Human/interview needed:
- External research needed:
- Implementation target:
```
