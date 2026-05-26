---
name: create-report
description: >
  Create project-aware evidence reports and report UIs from a given project,
  surface, artifact, or question. Use when the user asks to create a report,
  HTML/CSS report, project status report, page-purpose report,
  implementation/readiness report, source-of-truth audit, application
  inventory, review readout, or report-to-plan handoff that must apply
  best-practices-report while also using project-specific sources such as
  project-knowledge, monitor-sparta, test-interactions, ask persona reviews,
  dogpile research, review-design, review-code, review-prompt, and downstream
  plan-iterate instructions.
triggers:
  - create report
  - generate report
  - make an HTML report
  - create HTML CSS report
  - page purpose report
  - project status report
  - readiness report
  - report for this project
  - report for Sparta Explorer
  - report to plan-iterate
  - report with plan-iterate handoff
provides:
  - project-aware-report
  - report-orchestration
  - report-ui
  - plan-iterate-seed
  - evidence-report-handoff
composes:
  - best-practices-report
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
  - orchestration
  - validation
  - precision
  - project-state
---

# create-report

Create a project-specific report by orchestrating evidence sources, project
knowledge, reviewers, and deterministic checks. `$best-practices-report` is the
general report quality contract; `$create-report` decides which project-specific
inputs must feed the report for the requested target.

## Core Rule

Always compose `$best-practices-report` first. Do not duplicate or weaken its
rules. A `$create-report` output must satisfy the report contract: persona,
primary object, source of truth, evidence, findings, rationale, valid actions,
constraints, acceptance checks, non-claims, and a `$plan-iterate` seed when
follow-on work exists.

## Workflow

1. Define the report target:
   - project, product, page, route, artifact, code surface, prompt contract, or
     operational question;
   - intended reader/persona;
   - decision the report must support;
   - expected output format: Markdown, HTML/CSS, or React report surface.

2. Load the general contract:
   - read `$best-practices-report`;
   - use its required flow, anti-dashboard-theater rules, source inventory,
     finding/action contracts, and plan-iterate seed contract.

3. Resolve project-specific context:
   - use `$project-knowledge` for current goals, recent decisions, open
     questions, takeover notes, evidence pointers, and known blockers;
   - use `$project-knowledge`'s memory-backed recall path when available before
     relying on local files alone;
   - cite the exact project-knowledge file, memory result, or artifact used.

4. Select evidence producers by target:
   - UI/report/page/route: `$test-interactions` for live DOM evidence and
     screenshots; `$review-design` for persona-based visual review.
   - Code implementation: `$review-code` plus scoped files/diff and test logs.
   - Prompt contract: `$review-prompt` plus rendered fixture, expected
     response, validators, and consumer/schema.
   - Persona/compliance/expert judgment: real `$ask` runtime with request,
     status, events, and review artifacts.
   - External examples or repeated confusion: `$dogpile` with persona,
     rationale, and context.
   - SPARTA / Sparta Explorer: `$monitor-sparta` plus `$project-knowledge`.

5. Build the semantic model before layout:
   - persona;
   - primary object;
   - source of truth;
   - evidence;
   - findings;
   - valid actions;
   - blockers and unknowns;
   - acceptance checks;
   - non-claims;
   - next `$plan-iterate` seed.

6. Render only after the model is explicit:
   - prefer HTML/CSS for substantial human-facing reports;
   - keep the layout document-like, prose-first, and evidence-oriented;
   - avoid KPI cards, hero metrics, fake status badges, decorative charts, and
     dashboard shells.

7. Verify report outputs:
   - for HTML/React reports, inspect a rendered screenshot or CDP capture;
   - verify visible blockers, non-claims, source inventory, findings, and
     plan-iterate instructions appear in the default view;
   - record the screenshot/read artifact path when UI verification is required.

## Project-Specific Routing

### SPARTA / Sparta Explorer

Use this route for SPARTA, Sparta Explorer, Sparta Chat, F-36 corpora, QRAs,
controls, sources, URLs, supply chain, posture, coverage, or threat matrix.

Required sources:

- `$project-knowledge`: current SPARTA goals, active work, open questions,
  takeover notes, and evidence pointers.
- `$monitor-sparta`: monitor health/status or durable monitor artifacts.
- `$test-interactions`: live route/page evidence when reviewing Explorer UI or
  report surfaces.
- `$ask` persona review: Brandon for compliance/evidence adjudication, Nico for
  corpus maintenance and source/QRA workflows, or another explicit persona.
- `$dogpile`: external/competing product or project references when page
  purpose, workflow, or UX convention is under review.

Required SPARTA report sections:

- project goals served by the surface;
- owning persona and primary workflow;
- source-of-truth inventory;
- monitor buckets: `raw_candidates`, `gated_runnable`, `stored_qras`,
  `deterministic_skips`, and `failures` when coverage is discussed;
- status split: `Finished`, `Pending`, `Outstanding`, `Broken`, `Blocked`,
  and `Unproven`;
- page/surface contracts;
- findings tied to evidence;
- plan-ready next actions;
- new `$plan-iterate` instructions.

Do not substitute UI counts, dashboard status chips, or generic coverage
language for Arango-backed monitor evidence or project-goal evidence.

### Generic Project Reports

When no project-specific rule exists:

- use `$project-knowledge` to recover goals and state;
- use deterministic local artifacts before reviewer summaries;
- run domain review only when the target warrants it;
- mark missing project context as `Unknown` or `Blocked`;
- include the next `$plan-iterate` seed for actionable work.

## Required Output Skeleton

Use `$best-practices-report` for full details. `$create-report` requires at
least:

```md
# <Report Title>

## Report Summary
Overall finding, conclusion, evidence basis, highest-risk issues, immediate
next steps, and non-claims.

## Scope
Reviewed target, excluded scope, and evidence available.

## Project Context
Project goals, current state, recent decisions, open questions, and takeover
notes used for this report.

## Source-of-Truth Inventory
Files, monitor outputs, logs, screenshots, database/API/query artifacts,
reviewer receipts, and limitations.

## Findings
Evidence-backed findings with owner, rationale, impact, valid next actions,
acceptance check, and non-claims.

## Surface / Module Contracts
One contract per page, route, module, component, or report section.

## Finished / Pending / Outstanding / Broken / Blocked / Unproven
State split against project goals and evidence.

## Plan-Ready Next Actions
Action queue tied to finding IDs and acceptance checks.

## Plan-Iterate Seed
Objective, candidate phases, deterministic gates, domain review loops,
interaction evidence, ask/persona review, dogpile/reference research, human
decisions, and non-claims.

## New Plan-Iterate Instructions
Recommended phase id, acceptance contract, suggested graph, required evidence
artifacts, command patterns, stop conditions, and non-claims.

## Non-Claims
What the report does not prove.
```

## Plan-Iterate Handoff

The report should make the next `$plan-iterate` easy to create. Include:

- recommended phase id;
- objective;
- acceptance predicates;
- phase graph candidates;
- required commands or command patterns;
- evidence artifact list;
- applicable domain review loops;
- human-only decisions;
- stop conditions;
- non-claims.

If no follow-on phase is warranted, state why and cite the evidence. Do not end
with a vague recommendation to "make a plan."

## Fail-Closed Rules

- If project goals are unavailable, report project-goal status as `Unknown`.
- If monitor or validation artifacts are unavailable, report operational status
  as `Unknown` or `Blocked`.
- If screenshots do not visibly prove UI claims, mark visual proof as failed.
- If reviewer receipts are informal or missing runtime artifacts, do not cite
  them as `$ask`, `$review-design`, `$review-code`, or `$review-prompt` proof.
- If the report cannot produce a concrete plan-iterate seed for actionable
  findings, mark the report incomplete.
