---
name: best-practices-explain-project
description: >
  Standards for feature-level explainability packages: strict JSONL explainers,
  teleprompter notes, source/debugger stops, Excalidraw/SVG diagram bindings,
  common architecture interview questions, and end-of-work agent transparency.
triggers:
  - explain project best practices
  - feature explainer contract
  - interview cockpit standard
  - post-agent explainability
provides:
  - feature-explainer-contract
  - interview-cockpit-standard
composes:
  - debugger
  - create-architecture
  - create-svg
  - ops-excalidraw
  - live-evidence
  - agentic-evals
runtime_self_improvement: basic
disciplines:
  - developer-tooling
  - human-collaboration
  - ui-design-engineering
---

# Best Practices: Explain Project

Use this when substantial code or skill work must be explainable after it is built.
The output is a cockpit-ready explainability package, not another status report.

## Required artifact

Each project or skill may keep `docs/explain/explainers.jsonl`. Each line is one
strict `project.feature_explainer.v1` object validated with Pydantic
`extra="forbid"` before it drives UI, debugger, or diagram behavior.

Required fields:

- `feature_id`: stable dotted id.
- `title`: human-readable feature name.
- `question_family`: one of `walkthrough`, `scale`, `failure`, `optimize`,
  `tradeoff`, `confidence`, `custom`.
- `question`: interviewer/developer question this record answers.
- `teleprompter_points`: short oversized speaking points.
- `source_ranges`: exact files and line ranges.
- `diagram`: editable Excalidraw source by default, with optional rendered SVG.
- `proof_boundary`: what the explainer does and does not prove.

Optional fields:

- `debugger_stops`: only for runtime-state questions; name breakpoints, locals,
  and what the paused state proves.
- `runtime_launch`: command/config needed for a live walkthrough.
- `related_questions`, `confidence`, `last_verified`.

## Diagram rule

Prefer Excalidraw as the editable source when architecture may be adjusted live.
Use `$ops-excalidraw` to author/validate boards and `$create-svg` to render a
safe self-contained SVG preview. A finished SVG may be primary only when the
architecture is stable and no live editing is expected.

## Cockpit rule

An explainer record must be able to drive this route:

```text
question -> teleprompter points -> diagram node highlight -> VS Code source range -> optional debugger stop
```

`$debugger` is not decoration. Use it only when live runtime state answers the
question. Static scale/tradeoff questions use source and architecture first.

## End-of-work lifecycle

Run `$explain-project` after substantial agent work, like `$cleanup` or
`$project-state`, so the developer can inspect what changed through questions:
"walk me through it", "what breaks first", "how does it scale", and "how would
you optimize it".
