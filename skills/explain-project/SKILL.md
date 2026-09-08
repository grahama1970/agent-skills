---
name: explain-project
description: >
  Generate and validate end-of-work feature explainers for technical interviews
  and developer transparency: strict JSONL records, teleprompter notes,
  source/debugger bindings, editable Excalidraw architecture boards, optional
  SVG previews, and question routing.
triggers:
  - explain project
  - walk me through this code
  - interview cockpit
  - explain what the agent built
  - architecture interview prep
provides:
  - feature-explainer-jsonl
  - interview-cockpit-input
  - post-agent-explainability
composes:
  - best-practices-explain-project
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

# Explain Project

Create or validate a project-wide explainability package after substantial code
or skill work. This is for technical interviews and for developers who need to
understand what an agent changed.

Default output location: `docs/explain/explainers.jsonl` in the target project.
Each line is a strict Pydantic `project.feature_explainer.v1` record.

## Commands

```bash
skills/explain-project/run.sh validate docs/explain/explainers.jsonl
skills/explain-project/run.sh list docs/explain/explainers.jsonl
skills/explain-project/run.sh ask docs/explain/explainers.jsonl --question "What breaks first at scale?"
skills/explain-project/run.sh sample --output docs/explain/explainers.jsonl
```

## Record contract

A record maps a question to what the cockpit should show:

```text
question -> teleprompter notes -> Excalidraw/SVG node -> VS Code range -> optional debugger stop
```

Use Excalidraw as the default editable architecture source. Use SVG as a rendered
portable artifact when stable or when `$create-svg` verification has produced a
safe self-contained diagram. Use `$debugger` only when live runtime state answers
the question.

## Current scope

This MVP validates/list/searches explainer JSONL and emits a sample. It does not
launch the full multi-monitor cockpit, move windows, start Live Evidence, or run
VS Code debugger sessions. Those consumers must use the validated records.
