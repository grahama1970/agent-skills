---
name: acceptance-contract
description: >
  Turn a client brief, zip bundle, directory, or single requirements file into a
  typed acceptance-contract bundle with extracted requirements, acceptance
  checks, open questions, an immutable-goal draft, and a create-report-backed
  decision report. Use when users say acceptance contract, brief to
  requirements, freeze the goal, create immutable goal, amend immutable goal,
  build a Battle requirements bundle, or extract requirements from this bundle.
triggers:
  - acceptance contract
  - brief to requirements
  - freeze the goal
  - create immutable goal
  - amend immutable goal
  - build a Battle requirements bundle
  - extract requirements from this bundle
runtime_self_improvement: basic
provides:
  - acceptance-contract
  - requirements-extraction
  - immutable-goal-draft
  - report-generation
composes:
  - create-report
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - validation
  - precision
  - resilience
---

# acceptance-contract

Use this before implementation when a brief, ticket, email, README, zip bundle,
or evidence packet needs to become executable acceptance criteria.

## What it does

```bash
skills/acceptance-contract/run.sh extract <zip|directory|file> \
  --out /tmp/acceptance-contract \
  --project-name oai-trial \
  --goal-mode create
```

Outputs:

- `acceptance_bundle.json` — pydantic-validated source of truth
- `acceptance_report.json` — `create_report.report.v1` JSON
- `acceptance_report.md` — rendered through `$create-report`
- `IMMUTABLE_GOAL.draft.md` — draft goal text or amendment proposal

## Goal policy

Default behavior is **draft, not mutate**.

- `--goal-mode create` writes a new immutable-goal draft.
- `--goal-mode amend` writes an amendment proposal, not a silent edit.
- `--goal-mode none` extracts requirements without goal text.

A real immutable goal should be created or amended only after human approval.
That rule exists because oai-trial failed when implementation-defined tests
stood in for the client brief.

## Boundary

This skill extracts clear, source-backed requirements from supplied local files.
It does not claim the extracted contract is complete when the source bundle is
ambiguous. Ambiguity becomes `open_questions[]` and a Needs Changes report.

For Battle, pass the resulting bundle/profile into `$battle`; do not make Battle
invent the requirements.
