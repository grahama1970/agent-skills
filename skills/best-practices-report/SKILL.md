---
name: best-practices-report
description: >
  Produce evidence-bearing technical reports and report UIs without dashboard
  theater. Use when creating or reviewing reports, HTML/CSS report surfaces,
  implementation reviews, design reviews, application inventories, validation
  readouts, evidence ledgers, status/readiness reports, compliance/control
  summaries, source-of-truth audits, or issue-to-plan repair reports that must
  expose persona, primary object, source of truth, findings, rationale,
  blockers, valid actions, acceptance checks, non-claims, and plan-iterate
  handoff instructions.
triggers:
  - best practices report
  - evidence report
  - technical report
  - HTML report
  - report UI
  - report without dashboard theater
  - page purpose report
  - implementation review report
  - readiness report
  - source-of-truth audit
  - issue-to-plan report
  - report to plan-iterate
provides:
  - report-quality-contract
  - anti-dashboard-theater-rules
  - evidence-report-structure
  - report-to-plan-iterate-handoff
composes:
  - project-knowledge
  - monitor-sparta
  - test-interactions
  - ask
  - dogpile
  - review-design
  - review-code
  - review-prompt
  - plan-iterate
taxonomy:
  - reporting
  - validation
  - precision
  - compliance
  - ux
disciplines:
  - engineering-standards
  - content-creation
---

# best-practices-report

Use this skill to keep technical reports, HTML/CSS report surfaces, review
readouts, readiness summaries, and issue-to-plan handoffs evidence-first. A
report is not a dashboard. A report is a structured argument over source data.

For the full contract, read
`references/full-report-contract.md`. That reference contains the complete
rules for report flow, anti-dashboard-theater patterns, surface contracts,
finding/action traceability, project-specific source checks, SPARTA Explorer
requirements, and `$plan-iterate` handoff instructions.

## Core Invariant

Build the semantic report model before designing the layout:

1. Persona
2. Primary object
3. Source of truth
4. Evidence
5. Finding
6. Rationale
7. Valid action
8. Constraint, blocker, or unknown
9. Acceptance check
10. Non-claim

Only after those objects are explicit may you render Markdown, HTML, React, or
CSS.

## Required Report Shape

Every substantial report must include:

- top summary with overall finding, core conclusion, evidence basis,
  highest-risk issues, immediate next steps, and non-claims;
- scope;
- source-of-truth inventory;
- findings with evidence, rationale, impact, owner, valid next actions,
  acceptance check, and non-claims;
- surface or module contracts when surfaces are discussed;
- outstanding, broken, blocked, stale, missing, unknown, and unverified items;
- plan-ready next actions;
- `$plan-iterate` seed when follow-on work exists;
- non-claims;
- appendix or evidence details when needed.

Use the detailed templates in `references/full-report-contract.md` for
substantial reports.

## Anti-Dashboard-Theater Rules

Do not use KPI card grids, hero metrics, vague status badges, decorative
charts, generic dashboards, hidden blockers, or green/ready language without
fresh evidence.

Counts, statuses, charts, and summary numbers are allowed only when they resolve
to concrete evidence, source records, owners, valid actions, acceptance checks,
or source-of-truth queries.

Prefer paragraphs, description lists, compact tables, evidence blocks, and
plain section hierarchy over card grids.

## Evidence Rules

Every readiness, health, completion, correctness, coverage, compliance, or
production-safety claim must cite evidence such as validation logs, source
files, tests, screenshots, database/query results, API responses, review
receipts, phase ledgers, commit diffs, or exact source excerpts.

Absence of evidence is `Unknown`, `Unverified`, `Blocked`, `Stale`, or
`Partially Verified`; it is not success.

## Project-Specific Reports

For named projects, use `$project-knowledge` to identify goals, decisions,
open questions, takeover notes, and evidence pointers before assessing what is
finished, pending, outstanding, broken, blocked, or unproven.

For SPARTA, Sparta Explorer, Sparta Chat, F-36 corpora, QRAs, controls,
sources, URLs, supply chain, posture, coverage, or threat matrix reports,
include `$monitor-sparta` and project-knowledge evidence unless explicitly
scoped away from operational status. Separate monitor buckets such as
`raw_candidates`, `gated_runnable`, `stored_qras`, `deterministic_skips`, and
`failures` when coverage is discussed.

## Composition

Use other skills as evidence producers and reviewers; do not duplicate their
internals:

- `$test-interactions` for live UI interaction evidence, COTS/QID checks, and
  screenshot artifacts.
- `$ask` for artifact-bearing persona/oracle review, including Brandon, Nico,
  WebGPT, roundtable, parallel review, and deep review routes.
- `$review-design` for screenshot-backed design review.
- `$review-code` for scoped code review over files, diffs, tests, and
  contracts.
- `$review-prompt` for prompt-contract review with fixtures, expected
  responses, validators, and consumer/schema evidence.
- `$dogpile` for repeated blockers, external references, competing products,
  modern UX benchmarks, and current upstream research.
- `$plan-iterate` as the downstream phase controller when the report identifies
  actionable repair or implementation work.

## Plan-Iterate Handoff

Reports with actionable work must include a concrete `$plan-iterate` seed:

- recommended phase id;
- phase objective;
- initial acceptance contract;
- suggested phase graph;
- required evidence artifacts;
- required command patterns;
- domain review loops;
- interaction evidence;
- ask/persona review;
- dogpile/reference research;
- human-only decisions;
- stop conditions;
- non-claims.

If no follow-on phase is warranted, state the evidence-backed reason.

## Self-Check

Before finalizing a report, verify:

- the report is prose-first, not a card dashboard;
- every positive status has evidence;
- unknowns and blockers are visible in the default view;
- each surface has one owning persona;
- every count is traceable to records;
- every major finding maps to an action, decision, dependency, or non-action
  rationale;
- there is a source-of-truth inventory;
- there is a plan-ready action queue;
- there is a clear non-claims section;
- actionable findings include a `$plan-iterate` seed.
