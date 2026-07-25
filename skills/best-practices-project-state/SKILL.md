---
name: best-practices-project-state
description: >
  Standards and workflow for creating root-level PROJECT_STATE.md reports from
  local receipts, project knowledge, stale/aspirational audits, competitor
  research, and external reviewer evidence. Use when asked for project state,
  comprehensive project review, "what works and what is missing", stale code/doc
  assessment, competitive positioning, or a PROJECT_STATE.md deliverable.
triggers:
  - project state best practices
  - PROJECT_STATE.md
  - comprehensive project review
  - what works and what is missing
  - stale aspirational missing
  - competitive project comparison
provides:
  - project-state-report-standard
  - project-state-review-bundle
  - project-state-validation
composes:
  - project-knowledge
  - project-state
  - memory
  - ask
  - browser-oracle
  - brave-search
  - github-search
  - dogpile
  - best-practices-python
  - best-practices-skills
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
taxonomy:
  - assessment
  - research
  - documentation
  - validation
---

# Best Practices: PROJECT_STATE.md

Use this skill to produce a durable root-level `PROJECT_STATE.md` that a human,
nightly subagent, or reviewer can inspect without reconstructing the session.
The report is an evidence-backed project snapshot, not a status essay.

## Required Inputs

Collect these receipts before drafting:

- Current local sanity command and receipt, for example `bash scripts/sanity.sh`
  and `.artifacts/sanity/<timestamp>/summary.json`.
- `PROJECT_KNOWLEDGE.md` and, when available, `$project-knowledge read --refresh`.
- Old `$project-state` output only as an input signal; do not let it define the
  final structure when it is stale or Embry-specific.
- Git state: branch, remote, dirty tracked/untracked counts, and recent commits.
- Stale/aspirational audit: docs with TODO/future/planned language, unreferenced
  files, parse failures, missing imports, and known broken tests.
- Browser-oracle resolve/doctor receipt for the project.
- Research receipts from `$brave-search`, `$github-search`, and `$dogpile`.
- `$ask` WebGPT review artifacts for the assembled review bundle.

## Research Workflow

Run research before WebGPT review so the reviewer sees evidence, not just local
assumptions.

1. Use `$brave-search` for current product/library/research landscape.
2. Use `$github-search` for comparable repositories, code patterns, issues,
   README positioning, and maintenance signals.
3. Use `$dogpile` for multi-source synthesis and ambiguity handling. Preserve
   `dogpile_partial_results.json`, final Markdown/HTML reports, and provider
   degradation notes.
4. Build a review bundle with local receipts plus research outputs.
5. Use `$ask` through the real runtime for WebGPT or a broader panel. Attach
   the bundle content or a readable bundle file; a browser tab cannot inspect
   bare paths by itself.
6. Reconcile reviewer claims against local evidence before writing
   `PROJECT_STATE.md`.

## Required Report Shape

`PROJECT_STATE.md` must include these top-level sections:

1. `# Project State: <project>`
2. `## Executive Summary`
3. `## Evidence Receipts`
4. `## What Works`
5. `## Outstanding Gaps`
6. `## Aspirational Or Stale Material`
7. `## Missing Or Regressed Capabilities`
8. `## Competitive And Research Landscape`
9. `## Project Positioning`
10. `## Risks And Unknowns`
11. `## Recommended Next Actions`

Each material claim must cite a receipt path, command output, research artifact,
or reviewer artifact. If evidence is missing, write `not established` and name
the missing receipt.

## Claim Discipline

- Distinguish `working`, `partially working`, `not established`, `stale`,
  `aspirational`, and `missing`.
- Do not infer production readiness from mocked tests, empty logs, absent
  errors, or reviewer prose.
- Mark competitor/research claims with source artifacts and date.
- Keep project positioning sober: say where the project can own a niche only
  when local capabilities and external comparison support it.
- Do not hide failed checks. Failed tests and degraded providers belong in
  `Evidence Receipts` and `Risks And Unknowns`.

## Project-Knowledge Composition

After `PROJECT_STATE.md` is written and validated:

- Update `PROJECT_KNOWLEDGE.md` with a compact section pointing to the state
  report and the key new durable lessons.
- Run `$project-knowledge sync` when available so memory recall can find the
  state summary.
- Do not replace `PROJECT_KNOWLEDGE.md` with `PROJECT_STATE.md`; the former is
  rolling shared context, the latter is a dated assessment artifact.

## Validation

Run:

```bash
bash scripts/sanity.sh
uv run --project . python scripts/validate_project_state.py /path/to/PROJECT_STATE.md
```

The validator checks required sections and basic receipt-path evidence. It is a
format/evidence-floor gate only; it does not prove the project is healthy.

For live review readiness, run the opt-in gate:

```bash
bash scripts/sanity-live.sh /path/to/project
```

The live gate calls the real browser-oracle resolver and checks that the
research/review skill entrypoints needed by this workflow are present. It does
not replace the actual `$brave-search`, `$github-search`, `$dogpile`, or `$ask`
run receipts required for a final `PROJECT_STATE.md`.

## Nightly Use

Nightly subagents should be incremental:

- Reuse unchanged receipts when files and commands have not changed since the
  last valid state report.
- Rerun sanity, best-practices, research, and reviewer steps for changed files,
  changed dependencies, changed claims, stale receipts, or failed prior gates.
- Commit and push only the coherent state-report slice when validation and
  required local checks pass.
