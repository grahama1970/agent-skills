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

First command for implementation work:

```bash
skills/acceptance-contract/run.sh ensure <zip|directory|file> \
  --out /tmp/acceptance-contract \
  --project-name oai-trial \
  --goal-mode create
```

`ensure` is the mechanical guard: it validates an existing `acceptance_bundle.json`,
auto-extracts one when missing, and fails closed when the supplied source bundle
has changed since the frozen contract was written. Its JSON receipt includes an
`acceptance_contract.progress.v1` meter with `percent`, `checks`, `outstanding`,
and `next_steps`. Do not implement from a brief until `ensure` returns
`status=PASS` and the progress meter says what remains.

Pass the **client brief, zip bundle, or deliberately staged spec directory** as
input. The CLI refuses repository roots by default so implementation files cannot
silently become the acceptance source. Use `--allow-repo` only when the human
explicitly asks for a repository-wide contract.

For high-stakes client briefs, run a second-line `$ask` roundtable review on the
brief/zip plus `acceptance_bundle.json` before implementation. Include WebGPT as
one reviewer when available. Ask plainly: "Are these contract requirements
correct, and did we miss anything?" Require reviewers to check whether any client
obligation is missing from the frozen contract, especially representation
classes, typed values, boundary conditions, and disqualifying failure modes. The
review is advisory evidence; deterministic gates still own PASS/FAIL. The oai-trial
review found that typed-scalar coverage must also require canonical equivalence:
formatted policy strings, digit-only numeric scalars, decimal forms, scientific
notation, and SQLite numeric values cannot be separate acceptance universes.

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

Commands:

- `extract` always writes a fresh draft bundle/report from the supplied source.
- `ensure` validates or creates the frozen bundle and rejects stale source hashes.
- `validate` validates an existing `acceptance_bundle.json` only and prints the progress meter.
- `status` reads an existing `acceptance_bundle.json` and prints only the machine-readable progress meter.

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
It refuses repo roots by default because oai-trial failed when code-shaped checks
stood in for the delivered brief.

For Battle, pass the resulting `acceptance_bundle.json` as the arena
`acceptance_floor` and map each `acceptance_cases[].id` to one or more generator
case ids in the Battle campaign profile's `required_case_ids`. Those mapped cases
are the contract floor that must pass before fuzz or beyond-contract attacks can
be credited. Do not make Battle invent the requirements.
