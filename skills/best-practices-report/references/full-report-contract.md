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
---

# best-practices-report

## Purpose

Use this skill whenever producing a technical report, system design document, application inventory, architecture review, implementation review, UX review, source-of-truth audit, validation readout, or HTML/React report surface.

The goal is to produce a readable, evidence-bearing report that flows like a serious technical document. Do not produce "dashboard theater": large cards, hero metrics, decorative charts, vague badges, empty status indicators, or visually impressive layouts that do not expose evidence, rationale, ownership, constraints, and next actions.

A report is not a dashboard.
A report is a structured argument over source data.

## Non-Negotiable Rule

Build the semantic report model before designing the layout.

The required semantic model is:

1. Persona
2. Primary object
3. Source of truth
4. Evidence
5. Finding
6. Rationale
7. Valid action
8. Constraint / blocker / unknown
9. Acceptance check
10. Non-claim

Only after those objects are explicit may you render the report as Markdown, HTML, React, or CSS.

## When to Use This Skill

Use this skill for:

- technical reports,
- implementation reviews,
- design reviews,
- code review summaries,
- application inventories,
- architecture inventories,
- validation readouts,
- evidence ledgers,
- UI/UX audit reports,
- project status reports,
- system readiness reports,
- control or compliance summaries,
- HTML/CSS report mockups,
- React report surfaces,
- source-of-truth analysis,
- issue-to-plan repair reports.

Do not use this skill for ordinary casual answers, short one-off explanations, or creative writing unless the user explicitly asks for a report or report UI.

## Core Report Principle

Every report must answer, in readable prose:

1. What is true?
2. How do we know?
3. Who owns the surface, decision, or repair path?
4. What object is being manipulated, evaluated, or routed?
5. What actions are valid?
6. What is blocked, stale, missing, degraded, unknown, or unverified?
7. What should happen next?
8. What does this report not prove?

Prefer paragraphs, description lists, compact tables, evidence blocks, and clearly labeled sections over card grids.

## Anti-Dashboard-Theater Laws

### 1. Actionability Law

Counts, status indicators, badges, scorecards, and summary numbers are forbidden unless they resolve directly to at least one of:

- concrete evidence,
- a specific source record,
- a finite decision loop,
- a failing validation,
- an owner,
- an immediate valid action,
- an acceptance check,
- or a source-of-truth query.

Do not include vanity metrics.

Forbidden examples:

- "12 Active Systems" with no list of the 12 systems.
- "Healthy" without explicit validation timestamp and validator name.
- "High Risk" without rationale and evidence.
- "85% Complete" without a task ledger or completion predicate.
- "3 Critical Issues" without finding IDs and source artifacts.

Allowed examples:

- "3 unresolved schema failures" linked to exact failing objects.
- "Unknown: no validation run found after 2026-05-20."
- "Blocked: graph index missing `control_id` lookup."
- "P1: report summary is misleading because positive status chips are not bound to validation artifacts."

### 2. Fail-Closed Semantics

Never infer health from missing data.

Stale, missing, unknown, partial, or unverified source data must be explicitly marked as one of:

- `Missing`
- `Unknown`
- `Stale`
- `Unverified`
- `Partially Verified`
- `Blocked`
- `Degraded`
- `Needs Changes`
- `Needs Decision`

You are prohibited from defaulting any state to:

- `Healthy`
- `Green`
- `Complete`
- `Ready`
- `Passing`
- `Verified`

unless fresh validation evidence is present.

Every positive status must include:

- source of truth,
- validation method,
- validation timestamp or recency statement,
- and the exact predicate that passed.

### 3. Persona Isolation

Each report section or application surface must map to one primary persona.

Do not blend administrative control, analytical review, implementation editing, operator triage, and executive summary workflows into the same operational scope.

Bad:

> Admin dashboard where operators, reviewers, developers, and executives all manage workflow state.

Good:

> Corpus Maintenance Review Queue  
> Owner: Nico, corpus-maintenance operator  
> Purpose: Adjudicate unresolved corpus extraction failures before promotion.

### 4. Evidence Before Impression

Never write conclusions based only on visual appearance.

Forbidden evidence language:

- "The UI looks complete."
- "The design implies readiness."
- "No errors were visible."
- "It appears healthy."
- "The dashboard shows status."

Allowed evidence language:

- "The screenshot confirms the live surface still renders the previous shell."
- "The validation log contains no run after the schema change."
- "The diff adds a warning block but does not bind it to source records."
- "The report is unverified because the cited artifact is missing."

### 5. No Hidden Reality Rule

Do not hide blockers, unknowns, stale data, failed validations, or non-claims behind tabs, accordions, hover states, filters, or secondary panels.

Primary risks and blockers must be visible in the default view.

Progressive disclosure is allowed only for secondary evidence, raw logs, long excerpts, implementation details, or appendices.

## Output Format Policy

Prefer HTML-CSS for substantial human-facing reports when the user asks for a report, review surface, inventory, design assessment, application inventory, or implementation readout.

Markdown is acceptable for:

- CLI output,
- short reviews,
- plain text handoffs,
- strict automation contracts,
- or when the user explicitly requests Markdown.

HTML-CSS is preferred because it supports:

- clearer section hierarchy,
- semantic warning colors,
- evidence callouts,
- readable typography,
- compact metadata blocks,
- side notes without dashboard cards,
- print/export readability,
- and better scanning for broken, stale, missing, or unknown states.

However, HTML-CSS must remain a report document, not a dashboard.

The correct pattern is:

1. Build the semantic report model.
2. Define the surface contracts.
3. Identify evidence, unknowns, blockers, and valid actions.
4. Render the result as a readable HTML document.

Never begin from a dashboard layout.

## Required Report Flow

Use this structure unless the user provides a stronger one:

```md
# Report Title

## Report Summary

A compact, prose-first summary that states the main conclusion, evidence basis, highest-risk issues, immediate next steps, and non-claims.

## Scope

What was reviewed, what was not reviewed, and what evidence was available.

## Source-of-Truth Inventory

A compact table or description list of sources used.

## Findings

Each finding must include evidence, rationale, impact, owner, valid next actions, and non-claims.

## Surface / Module Contracts

Use the mandatory Surface Contract block for every proposed or reviewed surface.

## Outstanding / Broken / Unknown

A blunt list of what is not proven, not implemented, stale, missing, degraded, or blocked.

## Plan-Ready Next Actions

A finite action queue that can be converted directly into a `$plan-iterate`
phase, phase graph, or implementation plan.

## Plan-Iterate Seed

When the report finds implementation, validation, UX, code, prompt, compliance,
or source-of-truth work, include the initial `$plan-iterate` seed: objective,
phase candidates, deterministic evidence gates, applicable domain review loops,
human-only decisions, and non-claims. If no follow-on phase is warranted, state
the evidence-backed reason explicitly.

## Non-Claims

Explicitly state what the report does not prove.

## Appendix / Evidence Details

Raw supporting evidence, detailed logs, screenshots, query results, excerpts, or long tables.
```

## Mandatory Top Summary

Every substantial report must begin with a compact, prose-first summary.

The summary must not be a KPI dashboard, hero card grid, or decorative overview.

It must include:

1. **Overall Finding**
   - One of: `Ready`, `Needs Changes`, `Blocked`, `Degraded`, `Unknown`, or `Partially Verified`.
   - `Ready` is allowed only when the report has explicit readiness evidence.

2. **Core Conclusion**
   - One clear paragraph explaining the main conclusion.

3. **Evidence Basis**
   - One short paragraph naming the strongest source artifacts, validations, screenshots, logs, files, or reviewed objects.

4. **Highest-Risk Issues**
   - A short list of the most important blockers or degraded areas.
   - Each item must map to a later finding ID.

5. **Immediate Next Steps**
   - A short ordered list of the first actions needed to address the report.
   - Each action must map to a concrete finding, owner, object, and acceptance check.

6. **Non-Claims**
   - A brief statement of what this report does not prove.

Recommended format:

```md
## Report Summary

**Overall Finding:** Blocked / Needs Changes / Degraded / Unknown / Partially Verified / Ready

**Core Conclusion:**  
One clear paragraph explaining the report's conclusion.

**Evidence Basis:**  
One paragraph naming the actual evidence reviewed.

**Highest-Risk Issues:**

1. `[F-001]` Issue title — why it matters.
2. `[F-002]` Issue title — why it matters.
3. `[F-003]` Issue title — why it matters.

**Immediate Next Steps:**

1. `[A-001]` Concrete action tied to finding ID.
2. `[A-002]` Concrete action tied to finding ID.
3. `[A-003]` Concrete action tied to finding ID.

**Non-Claims:**  
This report does not prove X, Y, or Z unless explicitly evidenced below.
```

## Mandatory Surface Contract

For every page, module, component, report section, workflow surface, or UI proposal, output the following contract block.

Do not replace this with a vague summary.

Use this exact structure:

```md
### Surface Contract: <name>

| Contract Element | Required Content |
|---|---|
| System Surface Name | Clear, unhyped functional name of the view, module, or report section. |
| Owning Persona | The explicit human role/title responsible for this surface. |
| Core Purpose | A concise statement beginning with a strong verb explaining what the persona achieves here. |
| Primary Object | The exact artifact, record, entity, file, queue item, or database object manipulated or evaluated here. |
| Source of Truth | The database, file, graph index, API, registry, log, validation artifact, or human-owned source backing the data. |
| Valid Actions | A finite list of state changes, routing operations, edits, reviews, exports, or decisions available to the persona. |
| Outstanding / Broken / Constraints | Raw blockers, degraded data paths, missing validations, stale inputs, unresolved risks, or prerequisites. |
```

Important: this is a 7-element contract. Do not call it a 6-point contract.

## Finding Contract

Every major finding must use this structure:

```md
### Finding: <plain-language finding name>

**Finding ID:** F-001  
**Status:** Verified / Unverified / Stale / Blocked / Needs Decision / Needs Changes  
**Evidence:** Specific file, record, screenshot, log, validation result, source object, or observed behavior.  
**Rationale:** Why the evidence supports the finding.  
**Impact:** What breaks, degrades, confuses, delays, or risks the workflow.  
**Owner:** Persona or role responsible for action.  
**Valid Next Actions:** Finite list of acceptable next steps.  
**Acceptance Check:** How to verify that the issue has been addressed.  
**Non-Claims:** What this finding does not prove.
```

Do not write findings as vibes, impressions, or generic commentary.

## Plan-Ready Next Actions

Every report must include a plan-ready action queue that can be converted directly into an implementation plan.

Each action must include:

| Field | Required Content |
|---|---|
| Action ID | Stable ID such as `A-001`. |
| Related Finding | Finding ID such as `F-003`. |
| Action | Concrete verb-led task. |
| Owner Persona | Human or agent role responsible. |
| Primary Object | Exact file, component, record, surface, or artifact to change. |
| Rationale | Why this action is necessary. |
| Acceptance Check | How completion will be verified. |
| Dependencies | Required prior actions, data, or decisions. |
| Risk if Skipped | What remains broken, misleading, or unverifiable. |
| Suggested Priority | `P0`, `P1`, `P2`, or `P3`. |

Do not write vague actions such as:

- "improve dashboard",
- "clean up UI",
- "add better visibility",
- "make it modern",
- "enhance status indicators".

Use concrete actions such as:

- "Replace KPI card grid with evidence-backed finding articles."
- "Add stale-data warning state when validation timestamp is missing."
- "Create source-of-truth inventory table for corpus validation artifacts."
- "Add acceptance predicate for each report finding."
- "Remove green status badge until validation run is bound to source artifact."

## Plan-Iterate Seed Contract

For reports that identify actionable repair or implementation work, add a
`Plan-Iterate Seed` section after `Plan-Ready Next Actions`.

The seed is not a plan ledger and it is not closure. It is the report's
handoff into a new `$plan-iterate` phase or graph.

Required fields:

| Field | Required Content |
|---|---|
| Objective | One sentence describing the implementation or validation outcome the next phase must prove. |
| Candidate Phases | Ordered phase candidates, each tied to finding IDs and action IDs. |
| Deterministic Evidence Gates | Commands, validators, screenshots, manifests, DB/API queries, fixture checks, or artifact hashes required before acceptance. |
| Domain Review Loops | Which of `$review-design`, `$review-code`, `$review-prompt`, or another review skill applies, with persona, target, and required artifacts. |
| Interaction Evidence | Whether `$test-interactions` is required, the live surface URL or manifest target, and the expected `results.json` / screenshot artifacts. |
| Ask / Persona Review | Whether a real `$ask` runtime review is required, the persona or reviewer route, the target bundle, and expected ask artifact paths. |
| Dogpile / Reference Research | Whether `$dogpile` is required for external product/project references, repeated blockers, modern UX benchmarks, or competing implementations. |
| Human Decisions | Product, policy, credential, scope, or acceptance decisions the agent cannot safely infer. |
| Non-Claims | What the seed does not prove and what remains unvalidated until `$plan-iterate` runs. |

### New `$plan-iterate` Creation Instructions

The `Plan-Iterate Seed` must include clear creation instructions for the next
phase. Use this structure:

```md
### New Plan-Iterate Instructions

**Recommended phase id:** `<short-kebab-case-phase-id>`

**Phase objective:**  
One sentence describing the outcome the phase must prove.

**Initial acceptance contract:**
1. Predicate that must be proven with deterministic evidence.
2. Predicate that must be proven with reviewer artifacts.
3. Predicate that must remain explicitly non-claimed until later work.

**Suggested phase graph:**
1. Project-agent patch or artifact-generation node.
2. Deterministic validation node.
3. Applicable domain review node: `$review-design`, `$review-code`,
   `$review-prompt`, or a skip artifact with evidence.
4. Optional `$dogpile` reference/research node.
5. `$scillm` aggregation gate node.

**Required evidence artifacts:**
- Exact expected files, logs, screenshots, manifests, monitor outputs, or query
  results.

**Required commands or command patterns:**
- `$plan-iterate init` / `record-context` / `record-plan-graph` inputs.
- `$test-interactions`, `$review-design`, `$review-code`, `$review-prompt`,
  `$ask`, `$dogpile`, `$monitor-sparta`, or other commands that should run.

**Stop conditions:**
- What counts as `BLOCKED`, `HUMAN_REQUIRED`, or `INSUFFICIENT_EVIDENCE`.

**Non-claims:**
- What the new phase must not claim until the evidence gates pass.
```

If the report cannot provide these fields, the report must say which field is
missing and why. Do not leave the next phase as "make a plan" or "continue
cleanup." The report should be specific enough that a project agent can run
`$plan-iterate init`, record the context/graph, and begin the first
project-agent patch or validation node.

For `$plan-iterate`, the report's action queue should map cleanly to phase
inputs:

- UI / UX / report-surface work -> `$review-design` plus fresh screenshots and,
  when the surface is interactive, `$test-interactions` results.
- Code implementation work -> `$review-code` plus scoped diff, selected files,
  tests, build/typecheck/lint/runtime smoke, and known contracts.
- Prompt-contract work -> `$review-prompt` plus templates, rendered fixture,
  expected response, validators, consumer/schema, and smoke output.
- Compliance/security/source-of-truth work -> domain-specific validators,
  raw evidence artifacts, and persona review receipts.

Do not write `Plan-Ready Next Actions` as a vague backlog. Each action should
be executable as a project-agent patch iteration, a deterministic validation
gate, a read-only domain review loop, a `$dogpile` research escalation, or a
human decision.

## Composition Rules

Use other skills as evidence producers and reviewers. Do not duplicate their
internal behavior inside the report.

### `$test-interactions`

Require `$test-interactions` when the report reviews a live UI, report surface,
graph, pane, navigation, form, tab, keyboard flow, approval workflow, or
interactive evidence viewer.

The report must name:

- manifest path or required manifest target,
- live URL or app surface,
- persona used for review where applicable,
- `results.json` path,
- focused/container screenshot paths when relevant,
- deterministic failures and COTS/QID gaps,
- and how each failure maps to findings and actions.

Do not treat DOM assertions alone as visual proof. Screenshot artifacts must
visibly correspond to the claim being made.

### `$ask` Persona Review

Use the real `$ask` runtime when the report needs Brandon, Nico, WebGPT, a
roundtable, deep review, parallel review, or other persona/oracle judgment.

The report may cite `$ask` only by artifact, such as:

- request JSON,
- status JSON,
- events JSONL,
- `review.md`,
- `review.json`,
- controlled-tab or backend receipt when applicable.

Do not summarize an informal persona opinion as `$ask` evidence. `$ask` is the
artifact-bearing reviewer/oracle route; the report consumes its receipts.

### `$review-design`, `$review-code`, and `$review-prompt`

When the report identifies a domain review need, route it to the matching
review skill:

- `$review-design`: visual and interaction review. Requires screenshots; uses
  persona; composes `$test-interactions` for live DOM evidence.
- `$review-code`: code review. Requires scoped files/diff, context, expected
  contracts, and validation output.
- `$review-prompt`: prompt-contract review. Requires prompt templates,
  rendered fixture, expected response, validator/smoke command, and
  consumer/schema. Wording-only prompt reviews are incomplete.

The report must state whether each loop is required, not applicable with
evidence, or blocked by missing inputs. Review outputs are receipts, not phase
closure.

### `$dogpile`

Use `$dogpile` when external source-derived context can materially improve the
report or prevent repeated local guessing. This is especially appropriate for:

- repeated blockers or false-green loops,
- modern UX/reference patterns for serious workflow surfaces,
- competing products, projects, or repositories relevant to a surface such as
  Sparta Explorer,
- current documentation or upstream issues,
- ambiguous design or workflow conventions where outside examples can sharpen
  the contract.

For Sparta Explorer, `$dogpile` should be considered when page purpose,
persona workflow, evidence inspection, compliance review, or maintenance UX is
being redesigned or challenged as dashboard theater. The query must include
the persona/rationale/context so retrieved examples are interpreted against the
actual SPARTA workflow, not generic dashboard inspiration.

Dogpile output is advisory. The report must cite the report path,
partial-results JSON, useful findings, degraded provider lanes, and any
limitations. It must not claim product correctness from external examples.

## Finding-to-Action Traceability

Every major finding must map to at least one of:

- a next action,
- a required decision,
- a blocked dependency,
- or an explicit non-action rationale.

Every next action must map back to one or more finding IDs.

The report must not produce disconnected critique. It must produce a repairable action model.

## Priority Semantics

Use priority only for execution ordering, not drama.

- `P0`: Blocks truthful reporting, source-of-truth validation, safety, or core workflow correctness.
- `P1`: Blocks primary user workflow or creates misleading conclusions.
- `P2`: Degrades usability, clarity, evidence inspection, or maintainability.
- `P3`: Polish, refinement, or optional improvement.

Do not assign priority without rationale.

## Report-to-Plan Requirement

The report must be usable as the input to a repair plan.

A reader should be able to take the `Plan-Ready Next Actions` and
`Plan-Iterate Seed` sections and create a `$plan-iterate` phase or phase graph
without rereading the entire report.

If the report identifies issues but does not provide concrete next actions and
the next `$plan-iterate` seed, the report is incomplete unless it explicitly
states that no follow-on implementation phase is warranted and cites why.

## Writing Style Requirements

Use readable, explicit prose.

Prefer:

- paragraphs,
- description lists,
- compact evidence tables,
- numbered decision paths,
- concrete nouns,
- direct verbs,
- rationale after every recommendation,
- explicit caveats,
- short but complete sections.

Avoid:

- huge cards,
- hollow summaries,
- empty status badges,
- generic "insights",
- vague "monitoring",
- decorative grids,
- unexplained acronyms,
- marketing language,
- "modern dashboard" framing,
- large box layouts with one sentence per box.

Do not write:

- "This dashboard gives visibility..."
- "Users can quickly see..."
- "At a glance..."
- "A beautiful overview..."
- "Seamless experience..."
- "Modern analytics experience..."

Instead write:

- "This report section lets the corpus operator adjudicate unresolved extraction failures against the validation ledger."
- "The status is unknown because no validation artifact exists after the schema change."
- "The only valid actions are accept, reject, route to investigation, or mark blocked."
- "The UI must expose stale evidence because the source registry has no current validation timestamp."

## Typography and Legibility Rules

For HTML, React, or CSS report generation:

- Use a text-first document layout.
- Default to one column.
- Use two columns only when comparing two related objects.
- Avoid three-or-more-column card grids unless the content is genuinely tabular.
- Use a comfortable report width: approximately `860px–1080px`.
- Body font size should generally be `15px–17px`.
- Line height should generally be `1.5–1.7`.
- Use strong headings and visible section hierarchy.
- Use tables for structured comparisons, not layout theater.
- Use `<dl>`, `<dt>`, and `<dd>` for object metadata.
- Use `<blockquote>` or callout blocks for evidence and constraints.
- Use muted borders and background only to support reading.
- Do not bury important caveats in tiny gray text.
- Do not use low-contrast text for blockers or non-claims.

## HTML-CSS Report Mode

When generating HTML-CSS, produce a semantic report document.

Required layout:

- single-column or narrow two-column document flow,
- readable max-width, generally `860px–1080px`,
- prose-led sections,
- compact tables only where comparison is needed,
- `<main>` for the report shell,
- `<section>` for major report areas,
- `<article>` for findings or surface contracts,
- `<dl>` / `<dt>` / `<dd>` for metadata,
- `<blockquote>` or `.evidence-block` for source evidence,
- `.constraint-block` for broken, missing, unknown, stale, or blocked items,
- `.non-claims` section near the end,
- print-friendly CSS where practical.

Forbidden layout:

- KPI card grids,
- hero metric panels,
- fake dashboards,
- large empty containers,
- donut charts,
- generic status badges,
- traffic-light summaries without evidence,
- decorative icons,
- excessive whitespace,
- three-column "executive overview" theater,
- dashboard-style sidebars unless navigation is genuinely needed,
- full-width card grids with one sentence per card.

The page should feel like a well-designed technical memo, not an analytics product.

## Report Styling Rules

HTML-CSS reports should look like serious technical memos: dense, readable, calm, and evidence-oriented.

The visual hierarchy must guide the reader through:

1. conclusion,
2. scope,
3. evidence,
4. findings,
5. rationale,
6. constraints,
7. valid next actions,
8. non-claims.

Do not style the report like a SaaS analytics dashboard.

### Required Style Properties

Use:

- a prose-first document layout,
- restrained semantic color,
- clear heading hierarchy,
- compact metadata blocks,
- readable body text,
- visible evidence callouts,
- visible constraint callouts,
- dense but legible spacing,
- tables only for structured comparison,
- description lists for object metadata,
- muted borders instead of heavy card grids,
- clear focus states for interactive elements.

Avoid:

- huge cards,
- oversized numbers,
- hero panels,
- marketing gradients,
- generic "overview" tiles,
- empty whitespace theater,
- decorative charts,
- decorative icon grids,
- dashboard-style sidebars unless navigation is genuinely needed.

## Default Visual Tokens

Use a restrained technical-report palette.

### Text

- Body text: dark slate / near-black.
- Secondary text: muted slate.
- Labels: medium-weight slate.
- Links/actions: blue with underline or clear affordance.

### Semantic States

- Blocked / Broken: muted red.
- Stale / Warning / Degraded: muted amber.
- Unknown / Missing / Unverified: muted gray or violet.
- Evidence / Source of Truth: muted blue.
- Valid Action / Next Step: blue or slate.
- Verified: muted green only when fresh validation evidence exists.

Never use green to imply success without evidence.

### Typography

- Body size: `15px–17px`.
- Line height: `1.5–1.7`.
- Report width: `860px–1080px`.
- Use system fonts unless the user specifies otherwise.
- Avoid tiny labels, low-contrast gray text, and cramped tables.

## Semantic Color Rules

Color is allowed only to improve comprehension.

Use color to distinguish:

- Blocked / Broken: muted red.
- Stale / Degraded / Warning: muted amber.
- Unknown / Missing: muted gray or violet.
- Evidence / Source of Truth: muted blue.
- Valid Action / Next Step: neutral blue or slate.
- Verified: muted green only when fresh validation evidence is cited.

Never use green for assumed health.

Never use color as the only carrier of meaning. Every colored state must also include a text label.

## Visual Isolation of Errors

Outstanding issues, broken data loops, failed validations, technical limitations, and unverified claims must be visually highlighted.

Use warning variants such as:

- muted amber border for stale/degraded/warning,
- muted red border for blocked/broken,
- muted gray or violet border for missing/unknown,
- explicit labels in headings and text.

The reader should not have to hunt for reality.

## Lucide Icon Rules

Lucide icons are allowed only as semantic reading aids.

Rules:

- Every icon must be paired with text.
- Icons must not replace labels.
- Use icons sparingly: headings, warnings, evidence, actions, or constraints.
- Do not use icons as decorative filler.
- Do not create icon grids.
- Do not use icons to imply status unless the status is evidence-backed.

Recommended semantic mappings:

- `AlertTriangle` / `CircleAlert`: blockers, warnings, degraded paths.
- `FileText`: reports, source documents, review artifacts.
- `Database`: source-of-truth systems.
- `GitBranch`: workflow, DAG, lineage, routing.
- `ListChecks`: validation predicates or required actions.
- `Search`: investigation or evidence review.
- `ShieldCheck`: verified compliance only when evidence-backed.
- `CircleHelp`: unknown or missing data.
- `Clock`: stale or time-sensitive data.
- `UserRound`: owning persona.
- `Wrench`: implementation work required.

Never use `CheckCircle`, `BadgeCheck`, or similar positive icons unless validation evidence is explicit.

## Interactive Element Rules

Interactive elements are allowed only when they improve review, evidence inspection, comparison, or decision-making.

Allowed interactions:

- expand/collapse secondary evidence,
- filter findings by status, owner, source, or object type,
- jump from a finding to its evidence block,
- reveal raw source excerpts,
- compare two source records side by side,
- toggle between summary and detailed rationale,
- sort a table of concrete records,
- inspect chart source data,
- copy a finding, contract block, or next-action list,
- open a linked artifact, file, log, screenshot, or validation record.

Forbidden interactions:

- animated counters,
- decorative hover cards,
- fake drilldowns,
- charts without source records,
- filters over invented categories,
- tabs that hide critical blockers,
- collapsible sections that conceal primary conclusions,
- status badges with no evidence path,
- interactive elements that do not support a decision.

## Graph and Chart Rules

Charts are optional. Tables and prose are preferred unless a chart makes a real pattern easier to understand.

A chart is allowed only when it has:

- a named source of truth,
- real data,
- visible units,
- labeled axes,
- clear caveats,
- accessible text summary,
- and a decision the chart supports.

Every chart must answer:

1. What data is shown?
2. Where did the data come from?
3. What decision does this chart help make?
4. What is missing, stale, partial, or uncertain?
5. Where can the reader inspect the underlying records?

Forbidden charts:

- decorative donut charts,
- vague health gauges,
- progress rings,
- fake activity timelines,
- charts with invented data,
- charts that duplicate a simple sentence,
- unlabeled trend lines,
- "status distribution" charts with no action path.

Allowed charts:

- unresolved failures by validator,
- stale records by source system,
- open findings by owner,
- runtime by execution phase,
- coverage gaps by control family,
- queue age by adjudication state,
- validation failures over time from real logs.

## Chart Fallback Rule

If the chart does not change a decision, replace it with prose, a compact table, or an evidence block.

Preferred fallback order:

1. concise paragraph,
2. compact table,
3. description list,
4. evidence callout,
5. chart only when visual comparison materially improves understanding.

## Interactive Graph Requirements

Interactive graphs may be used only when the interaction reveals underlying evidence.

Every interactive graph must provide:

- hover or click access to exact source records,
- a visible plain-language interpretation,
- a table fallback,
- keyboard-accessible controls,
- non-color-only labels,
- and an explicit caveat for missing or stale data.

Graph interactions should support review actions such as:

- selecting a failing object,
- drilling into a source record,
- comparing owners,
- isolating stale data,
- showing validation history,
- or exporting the underlying records.

Do not create interactive graphs for visual polish.

## Accessibility Requirements

For HTML, React, or CSS report surfaces:

- Use semantic headings in order.
- Do not skip heading levels for visual effect.
- Use visible focus styles.
- Ensure contrast is sufficient for body text and labels.
- Do not rely on color alone for state.
- Pair icons with text labels.
- Provide table captions or clear preceding context.
- Use `aria-expanded` for disclosure controls.
- Avoid hover-only evidence.
- Ensure charts have text summaries and table fallbacks.

## Preferred HTML Report Components

Use these components before inventing new layout patterns:

- `ReportHeader`
- `ReportSummary`
- `ExecutiveFinding`
- `ScopeBlock`
- `SourceOfTruthInventory`
- `FindingArticle`
- `SurfaceContract`
- `EvidenceBlock`
- `ConstraintBlock`
- `DecisionPath`
- `ActionList`
- `NonClaims`
- `Appendix`

Avoid generic components named:

- `Dashboard`
- `OverviewGrid`
- `MetricCard`
- `StatsPanel`
- `InsightsCard`
- `HealthWidget`
- `ActivityWidget`
- `HeroMetric`

## Evidence Rules

Every claim of readiness, health, completion, correctness, coverage, or production safety must cite or name evidence.

Acceptable evidence includes:

- validation logs,
- source files,
- test output,
- screenshots,
- database records,
- graph query results,
- API responses,
- review receipts,
- ledger entries,
- commit diffs,
- manually identified source artifacts,
- exact source excerpts.

Unacceptable evidence:

- "The UI looks complete."
- "The design implies..."
- "The dashboard shows..."
- "The system appears healthy."
- "No errors were visible."
- "It seems done."

Absence of evidence must be reported as unknown, not success.

## Source-of-Truth Inventory

Every substantial report must include a source-of-truth inventory.

Required fields:

| Field | Required Content |
|---|---|
| Source ID | Stable source identifier, such as `S-001`. |
| Source Name | File, database, API, log, screenshot, registry, or artifact name. |
| Type | File, screenshot, DB record, graph query, API response, validation log, human-provided note, etc. |
| Recency | Fresh / stale / unknown, with timestamp if known. |
| Used For | Which findings or surface contracts rely on it. |
| Limitations | Missing scope, stale areas, partial data, unverified assumptions. |

## Project-Specific Source Checks

When a report is about a named project or product surface, read the project's
current goals before assessing what is finished, pending, outstanding, broken,
or blocked.

Use `$project-knowledge` as the coordination layer:

- recall project knowledge from `/memory` first when available,
- read the human-facing `PROJECT_KNOWLEDGE.md` projection when present,
- identify active goals, recent decisions, open questions, takeover notes, and
  evidence pointers,
- distinguish project goals from implementation status,
- and cite the exact project-knowledge source or memory recall used.

Do not treat a rendered page, dashboard, or report shell as proof that a project
goal is finished. A goal is finished only when the project-knowledge goal maps
to deterministic evidence, accepted phase ledgers, monitor state, or review
artifacts that prove the goal's acceptance predicate.

### SPARTA / Sparta Explorer Reports

When the report is about SPARTA, Sparta Explorer, Sparta Chat, SPARTA Coverage,
F-36 corpora, QRAs, controls, sources, URLs, supply chain, posture, or threat
matrix, include `$monitor-sparta` and project-knowledge state in the source
inventory unless the report is explicitly scoped away from operational status.

Required SPARTA source checks:

1. Project goals: read or recall current SPARTA project goals, active work,
   open questions, and takeover notes from `$project-knowledge`.
2. Monitor state: use `$monitor-sparta` health/status outputs or durable
   monitor artifacts when available.
3. Coverage semantics: separate `raw_candidates`, `gated_runnable`,
   `stored_qras`, `deterministic_skips`, and `failures`; do not collapse them
   into one "remaining" or "coverage" number.
4. Coverage lanes: identify which Sparta Explorer Coverage lanes are relevant:
   QRA Generation, Prompt Health, Monitor Health, UX Coverage, Python
   Fallbacks, Source/Text/QRA Coverage, and Source/Embedding Coverage.
5. Arango-first integrity: treat SPARTA monitor and data integrity as
   ArangoDB-first; do not substitute DuckDB or UI counts for corpus health.
6. Review-gated mutation: mark corpus mutations, prompt promotions, QRA
   generation, source backfills, embedding backfills, and threshold changes as
   review-gated unless explicit approved apply artifacts exist.
7. Persona workflow: map each Explorer page to its owning persona and purpose,
   especially Brandon for compliance/evidence adjudication and Nico for corpus
   maintenance pages such as Controls, Sources, URLs, and Coverage.
8. State split: publish a visible table or section separating `Finished`,
   `Pending`, `Outstanding`, `Broken`, `Blocked`, and `Unproven` against the
   project goals and monitor evidence.

For Sparta Explorer page-purpose reports, the report must answer:

- Which project goals does this page serve?
- Which persona owns the page's primary workflow?
- Which source of truth backs the page?
- What is finished with evidence?
- What is pending or outstanding?
- What is broken, blocked, stale, or unproven?
- Which `$monitor-sparta` lane, `$test-interactions` manifest, `$ask` persona
  review, `$review-design`, `$review-code`, `$review-prompt`, or `$dogpile`
  step should feed the next `$plan-iterate` phase?

If `$monitor-sparta` or project-knowledge evidence is unavailable, the report
must state `Unknown` or `Blocked` for operational status rather than filling the
gap with dashboard-style summaries.

## Readiness Semantics

Use readiness labels carefully.

| Label | Meaning |
|---|---|
| Ready | Evidence proves required predicates passed. |
| Partially Verified | Some predicates are proven, but important scope remains unverified. |
| Needs Changes | Concrete issues exist and should be fixed. |
| Degraded | System works partially but has broken, stale, or weak paths. |
| Blocked | Required prerequisite, evidence, source path, or implementation is missing. |
| Unknown | No reliable evidence exists. |

Do not use `Ready` when any P0 issue remains open.
Do not use `Verified` without fresh evidence.

## Implementation Advice for Codex

When asked to create a report UI, do not begin with layout.

Begin by defining:

1. personas,
2. primary objects,
3. source-of-truth records,
4. valid actions,
5. evidence model,
6. broken or unknown states,
7. findings,
8. plan-ready actions,
9. non-claims,
10. report sections.

Only after the semantic model is clear may you produce HTML, React, or CSS.

The UI should express the object model.
The object model must not be reverse-engineered from a visual dashboard layout.

## Anti-Pattern Rewrite Rules

If the requested or generated design contains dashboard theater, rewrite it into report form.

| Dashboard Theater | Replace With |
|---|---|
| KPI card grid | Report summary with evidence-backed finding IDs. |
| Hero metric | Prose conclusion with source-of-truth citation. |
| Status badge | State label plus evidence, timestamp, predicate, and next action. |
| Donut chart | Compact table unless the chart changes a decision. |
| Activity chart | Validation history table with source logs. |
| Overview tiles | Findings list with rationale and impact. |
| Health panel | Readiness section with fail-closed semantics. |
| Generic dashboard | Technical memo report shell. |
| Hidden details drawer | Visible blocker/unknown section plus optional appendix. |

## Required Self-Check Before Final Output

Before finalizing any report or report UI, verify:

- Does the report begin with a top summary?
- Does every positive status have evidence?
- Are unknowns explicitly labeled?
- Are stale or missing data paths visible?
- Does each surface have one owning persona?
- Is every count traceable to records?
- Are valid actions finite and concrete?
- Are blockers visually and textually prominent?
- Does the report read like prose rather than a card dashboard?
- Are charts used only when they support a decision?
- Are icons semantic and paired with text?
- Is there a source-of-truth inventory?
- Is there a plan-ready next action queue?
- Does every major finding map to an action, decision, dependency, or non-action rationale?
- Is there a clear `Non-Claims` section?

If any answer is no, revise before final output.

## Completion Gate

A report is incomplete if it lacks any of:

- top summary,
- scope,
- source-of-truth inventory,
- findings with evidence and rationale,
- surface contracts when surfaces are discussed,
- outstanding / broken / unknown section,
- plan-ready next actions,
- non-claims.

An HTML report is incomplete if it uses visual polish to imply certainty that is not backed by evidence.

## Default Output Preference

Default to HTML-CSS for substantial human-readable reports.

Default to Markdown for short reports, command-line handoffs, strict text-only automation, or when the user requests Markdown.

When generating HTML/React, preserve report semantics with:

- headings,
- paragraphs,
- description lists,
- compact tables,
- warning callouts,
- evidence blocks,
- restrained icon usage,
- optional evidence-driven interactivity.

Do not generate a generic dashboard shell.

## One-Sentence Invocation

Use the best-practices-report skill. Treat this as a semantic technical report, not a dashboard. Do not create KPI cards, hero metrics, status badges, or charts unless each resolves to source evidence, a named object, an owner, and a valid decision/action path.
