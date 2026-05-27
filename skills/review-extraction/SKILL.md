---
name: review-extraction
description: >
  Review PDF/document extraction evidence bundles. Use for golden-slice page reviews,
  pdf_oxide/PDF Lab extraction comparison, element-family coverage checks, and
  deciding whether mismatches belong to core extractor, document preset, downstream
  semantic parser, second-pass adjudication, or human decision. This is an evidence
  review skill, not a code review skill.
triggers:
  - review extraction
  - extraction review
  - review pdf extraction
  - pdf lab golden slice
  - golden-slice review
  - element family coverage
  - compare pdf_oxide output
  - extraction artifact bundle
  - review page extraction
metadata:
  short-description: Review PDF extraction golden-slice bundles
provides:
  - extraction-review
  - golden-slice-review
  - element-family-coverage-review
composes:
  - best-practices-agent
  - best-practices-plan
  - review-plan
  - review-code
  - pdf-screenshot
  - scillm
  - memory
taxonomy:
  - validation
  - evidence
  - pdf
---

## Standard Review Iteration Parameters

This `review-*` skill follows the shared contract in
`skills/.system/review-iteration-contract.md`.

Canonical parameters:

- `--max-rounds N`
- `--output-dir PATH`
- `--ask-gate`
- `--ask-model MODEL` (default `gpt-5.5`)
- `--ask-reasoning LEVEL` (default `high`)
- `--ask-timeout SECONDS`
- `--ask-focus LABELS`

When `--max-rounds > 1` is supplied, the skill must behave as a bounded
gate-producing controller or fail closed if that mode is not implemented. The
canonical gate artifact is `review_result.json` with verdict
`PASS`, `NEEDS_CHANGES`, `BLOCKED`, or `INSUFFICIENT_EVIDENCE`.

> STOP. READ THIS ENTIRE SKILL.MD BEFORE REVIEWING OR GENERATING EXTRACTION RESULTS.

# /review-extraction

Review extraction evidence bundles for a single page, candidate, or element family.

This skill exists to prevent project agents from bespoke-generating ad hoc extraction
reports, fake second-pass reviews, dashboard-like closure pages, or heuristic-to-finding
pipelines.

Use this when the question is:

```text
Human expected X on the page.
pdf_oxide / extractor emitted Y.
Do we agree?
If not, who owns the fix: core extractor, document preset, downstream semantic parser,
second-pass visual adjudicator, or human decision?
```

## Non-goals

This skill does NOT:

- review source-code diffs; use `/review-code` for that.
- mutate presets, ledgers, core extractor code, or matrices.
- declare full-document coverage from one page.
- infer expected counts from extracted counts.
- run broad LLM batches.
- accept dashboard/report status as proof.

## Required input bundle

A reviewable extraction bundle MUST be a ZIP or directory with this shape:

```text
golden_slice_<id>/
  manifest.json
  review_bundle.md
  command_log.txt

  images/
    human_labeled_page.png          # if human annotated the page
    page_clean.png                  # rendered source page
    pdf_oxide_overlay.png           # extractor bboxes overlaid on page
    element_crops/
      ...

  json/
    page_identity.json
    expected_elements.json
    pdf_oxide_raw_page.json
    pdf_oxide_release_page.json
    golden_slice_comparison.json
    mismatches_by_owner.json

  tables/
    extracted_elements_table.md
    golden_slice_comparison.md

  optional_code/
    git_diff.patch                  # only if tooling code changed
    changed_files.txt               # only if tooling code changed
    test_output.txt                 # only if tooling code changed

  blocked_on.md                     # only when sent under a stop-condition trigger
  json/
    blocked_on.json                 # canonical machine-readable form of the same
```

When the bundle ships under a stop-condition trigger (see "Iteration stop
conditions" and PROJECT_KNOWLEDGE.md §10), the agent MUST include
`blocked_on.md` at the top level AND `json/blocked_on.json` with the
canonical structure. The reviewer reads `blocked_on.md` first.

If `optional_code/` exists, the artifact review is not enough. The changed code
also needs a separate `/review-code` review.

## Required manifest fields

`manifest.json` MUST include (schema v2 — WebGPT 2026-05-13):

```json
{
  "schema_version": "review_extraction.golden_slice.v2",
  "release_mode": true,
  "apply_mode": "release",
  "staging_entries_used": false,
  "llm_used": false,
  "extraction_code_mutated": false,
  "preset_or_ledger_mutated": false,
  "matrix_mutated": false,
  "review_tooling_code_mutated": false,
  "human_labeled_page_image_present": true,
  "optional_code_present": false
}
```

Additional identifying / provenance fields (`slice_id`, `source_pdf`,
`source_pdf_sha256`, `human_claim`, `zero_based_page_index`,
`one_based_pdf_page_number`, `printed_page_label`, `created_at`,
`created_by`, `ledger_used`, `page_dimensions_px`, `crop_count`,
`artifact_paths`) SHOULD also be present.

### Mutation-flag rules

The single ambiguous `code_or_preset_mutated` flag from v1 is **DEPRECATED**
and MUST NOT be emitted by a v2 bundle.

If `optional_code_present=true`, then the specific mutation flag must be truthful:

- `review_tooling_code_mutated=true` when only the bundle generator changed.
- `extraction_code_mutated=true` when pdf_oxide / core extraction changed.
- `preset_or_ledger_mutated=true` when the document preset or promotion ledger changed.
- `matrix_mutated=true` only when a closure/status matrix was intentionally regenerated.

These four flags are independent. `optional_code_present == true` implies
`review_tooling_code_mutated == true` but does **NOT** imply
`extraction_code_mutated` or `preset_or_ledger_mutated`.

## Required expected-elements shape (v2)

Each row in `expected_elements.json::expected_elements[]` MUST have at minimum
`family` and `label`. The following optional fields tighten matcher behavior
and SHOULD be supplied when the human can:

```json
{
  "family": "section_heading",
  "label": "INTRODUCTION",
  "text_hint": "INTRODUCTION",
  "bbox_hint": null,
  "allowed_types": ["section_heading"],
  "match_strategy": "text_exact | text_contains | text_contains_or_bbox_region | type_only"
}
```

Without `text_hint` the matcher falls back to family/type synonyms which
produce many `ambiguous_multiple` rows (the classic "all 11 rows ambiguous"
failure mode).

## Required comparison table

`tables/golden_slice_comparison.md` MUST include these columns (schema v2 —
4-bucket classification):

```text
expected_family
human_label
match_status            # matched | ambiguous_multiple | missing | extra_extractor_element
candidate_matches       # list of {id, type, block_type, match_basis}
best_match_id           # ONLY set when match_status == matched
reviewer_action_required
match_basis             # text_hint | bbox_hint | allowed_types | type_synonym | fallback
type_match              # bool
text_match              # bool
bbox_match              # n/a (no human bbox) | true | false
notes
owner_if_wrong          # REVIEWER_FILL
next_step               # REVIEWER_FILL
```

### Match-status rules

- `matched`: exactly one deterministic candidate (single type+text agreement).
- `ambiguous_multiple`: ≥ 2 candidates that pass the matcher. **Not success.**
  Reviewer must narrow to a `best_match_id` (or reject all).
- `missing`: zero candidates.
- `extra_extractor_element`: an emitted element that is NOT paired with any
  expected row.

Rules:

- `best_match_id` may be set **only** when `match_status == matched`.
- `reviewer_action_required` MUST be `true` for `ambiguous_multiple`,
  `missing`, and every `extra_extractor_element`.
- `ambiguous_multiple` MUST NOT be counted as success in any summary.

### Matcher precedence (v2)

The runner SHOULD evaluate candidates in this order; first hit wins for the
`match_basis` label:

1. `text_hint` substring (case-insensitive, whitespace-normalized)
2. `bbox_hint` (when present, intersection-over-union ≥ 0.5)
3. `allowed_types` membership (type must be one of the allowed)
4. Family/type-synonym fallback (the v1 conservative path)

Allowed `owner_if_wrong` values:

```text
no_change
pdf_oxide_core
nist_preset_ledger
downstream_semantic_parser
second_pass_visual_adjudicator
human_decision
```

## Collaboration model

This skill assumes this operating model:

```text
Human labels the page and states intent.
WebGPT / reviewer is the reasoning layer and writes the plan.
Project agent is the local executor / code-runner and evidence producer.
Deterministic gates decide closure.
```

The reviewer must not merely say "fix it." When defects are found, the reviewer
returns a complete execution plan that the project agent can follow without
inventing strategy.

The project agent then implements exactly that plan, reruns extraction, and
resubmits an updated ZIP bundle plus any code-review materials. The loop
repeats until the actual JSON/output matches the human-expected extraction
contract or until the reviewer stops the loop for a human/product decision.

## Golden-slice review protocol

1. **Human labels representative page(s).**
   The human identifies visible expected elements such as headers, headings,
   paragraphs, bullet lists, footnotes, figures, tables, callouts, or requirements.

2. **Project agent produces evidence only.**
   The project agent renders the page, runs release-mode extraction, generates overlay
   images, crops, JSON, and comparison tables. It must not patch extraction code,
   presets, ledgers, matrices, or statuses while producing the evidence bundle.

3. **Reviewer compares expected vs actual.**
   The reviewer answers:
   - Did pdf_oxide emit the expected element?
   - Is the type correct?
   - Is the bbox/crop correct?
   - Is the text/payload correct?
   - If wrong, who owns the fix?

4. **Reviewer outputs a complete plan.**
   The reviewer must provide executable instructions for the project agent. Do not
   leave the project agent to infer the repair strategy.

5. **Project agent implements and resubmits.**
   The project agent applies only the approved changes, reruns the same golden slice,
   and sends back a new ZIP bundle with updated JSON, overlays, reports, and optional
   code review artifacts.

6. **Iterate until the JSON matches the expected contract.**
   The reviewer/project-agent loop continues until the release-mode extraction JSON
   and comparison table match the human-expected page contract, or until the reviewer
   explicitly stops the loop for a human/product decision.

7. **Deterministic rerun proves closure.**
   No status changes without rerun, fixture, and gate proof.

## Review output format

The reviewer MUST return this structure:

```text
Verdict: APPROVE_EVIDENCE | NEEDS_MORE_EVIDENCE | REJECT_BUNDLE

Page identity:
- zero-based page index:
- one-based PDF page:
- printed label:

Extraction summary:
- expected elements:
- matched:
- ambiguous:
- mismatched:
- missing:
- extra extractor elements:

Mismatches by owner:
- pdf_oxide_core:
- nist_preset_ledger:
- downstream_semantic_parser:
- second_pass_visual_adjudicator:
- human_decision:

Blocking issues:
- ...

Complete plan for project agent:
1. Scope and non-goals
2. Owner route for each mismatch
3. Files/scripts to change or inspect
4. Exact implementation steps
5. Required rerun command
6. Required ZIP contents for resubmission
7. Tests/gates to run
8. Stop conditions
9. What not to mutate

Next action:
- one concrete action only
```

If the verdict is `NEEDS_MORE_EVIDENCE`, the complete plan is an evidence plan.
If the verdict is `APPROVE_EVIDENCE` and defects are found, the complete plan
must specify the next owner route:

- `pdf_oxide_core`
- `nist_preset_ledger`
- `downstream_semantic_parser`
- `second_pass_visual_adjudicator`
- `human_decision`

## Complete plan requirements

The complete plan MUST be precise enough for a project agent to execute without
inventing strategy. It must include:

- the specific owner route for every defect class,
- exact files or commands when known,
- the artifact bundle expected after execution,
- deterministic gates required before any status changes,
- a prohibition on unrelated mutations,
- required resubmission ZIP contents,
- a canary-before-batch rule for any expansion.

Bad (rejected):

```text
Fix the extractor and rerun.
```

Good (accepted):

```text
Implement evidence-only R3 bundle changes:
- update manifest split flags in build_golden_slice_bundle.py
- add text_hint matching to expected_elements_v2.json
- regenerate GS001 zip
- do not patch pdf_oxide, preset, ledger, matrix, or call an LLM
- return R3 ZIP plus code-review bundle
```

## Iteration stop conditions

Stop the loop and ask the reviewer/human when:

- the expected page contract is ambiguous,
- a proposed fix requires product/semantic judgment rather than code evidence,
- the same mismatch persists after two implementation rounds,
- a proposed fix would broaden scope beyond the current golden slice,
- a core-vs-preset ownership question lacks a deterministic reproducer,
- the project agent cannot produce the required resubmission ZIP.

## `blocked_on` payload — structural required when a stop condition fires

When the agent sends a bundle under a stop-condition trigger, the bundle MUST
carry a structured `blocked_on` payload. Two artifacts, identical content:

- `blocked_on.md` (top-level, human-readable)
- `json/blocked_on.json` (machine-readable; canonical)

And the manifest MUST set `blocked_on` to a non-null object referencing the
six required fields below.

### Required fields

```json
{
  "schema_version": "review_extraction.blocked_on.v1",
  "stop_condition_id": "core_vs_preset_ownership_lacks_reproducer",
  "where_blocked": [
    {
      "comparison_row": 2,
      "expected_family": "side_watermark_or_page_chrome_noise",
      "detail": "text matches blocks 3/4/5 but typed paragraph_block/list — strict allowed_types(header_footer_noise) filter excluded them"
    }
  ],
  "specific_question": "For each missing row, name the owner route (pdf_oxide_core | nist_preset_ledger | downstream_semantic_parser | second_pass_visual_adjudicator | human_decision) AND the exact next implementation step.",
  "artifacts_to_consult": [
    "tables/golden_slice_comparison.md",
    "images/pdf_oxide_overlay.png",
    "images/element_crops/actual_p27_block_2.png",
    "json/pdf_oxide_release_page.json"
  ],
  "what_i_will_NOT_do_without_decision": [
    "do not patch src/extractors/*",
    "do not author a ledger entry",
    "do not mutate the closure matrix"
  ],
  "what_decision_unblocks": [
    "implement the named routes per the reviewer's plan",
    "regenerate the bundle as R(n+1)",
    "resubmit"
  ]
}
```

### Field rules

- `stop_condition_id`: one of the six bullets in "Iteration stop conditions"
  (snake_case identifier, e.g. `expected_contract_ambiguous`,
  `requires_product_judgment`, `mismatch_persists_after_two_rounds`,
  `scope_would_broaden`, `core_vs_preset_ownership_lacks_reproducer`,
  `cannot_produce_resubmission_zip`).
- `where_blocked`: a list — not prose. Each entry names a SPECIFIC artifact
  location (comparison row, element_id, file/line) — not "extraction is bad."
- `specific_question`: the exact decision the reviewer must make. Not "what
  should I do." A precise yes/no/route question.
- `artifacts_to_consult`: explicit paths INSIDE the bundle the reviewer
  should open first. Must exist on disk.
- `what_i_will_NOT_do_without_decision`: the guardrails — exactly which
  mutations the project agent is refusing pending the answer.
- `what_decision_unblocks`: what the next work round looks like once the
  reviewer answers.

### Hard rule

> If a bundle is sent under a stop-condition trigger but does NOT carry
> `blocked_on.md` + `json/blocked_on.json` AND `manifest.blocked_on != null`,
> the bundle is malformed and the auto-send must be rejected. No blocked_on
> payload → no auto-send.

The `review_bundle.md` SHOULD prepend a §0 "Asking for" block when blocked_on
is set, summarizing `specific_question` and pointing at the structured
payload.

## Loop convergence — what "done" means

> **Project agent implements the reviewer's complete plan, reruns extraction,
> and resubmits a new ZIP bundle with updated JSON, overlays, reports, and
> any code diffs. The reviewer/project-agent loop repeats until release-mode
> extraction JSON matches the human-expected page contract, or the reviewer
> stops the loop for a human/product decision.**

The convergence criterion is: the **release-mode** `pdf_oxide_release_page.json`
matches the human-expected contract encoded in `expected_elements.json`. Not
the raw JSON; the release JSON. Not a markdown summary; the actual JSON.

### Routing constraint (must be honored, not bypassed)

The project agent must NOT "force" the extractor to match the annotation
through hacks. Each mismatch routes to a specific owner; the project agent
implements the route the reviewer named and reruns:

- `pdf_oxide_core` — generic extractor bugs (affects multiple documents).
- `nist_preset_ledger` — document-specific typing / grouping / suppression.
- `downstream_semantic_parser` — requirements / control IDs / SPARTA meaning.
- `second_pass_visual_adjudicator` — unresolved visual/semantic ambiguity.
- `human_decision` — product / acceptance ambiguity.

The project agent does **not** decide that routing on its own. It implements
the reviewer's named route and reruns. If the routing call is unclear, the
agent stops and re-asks the reviewer per the Iteration stop conditions above.

## Iterative extraction-fix loop

After WebGPT/reviewer returns a complete plan, the project agent implements
only that plan, reruns the same golden slice, and resubmits a new ZIP bundle.

Each resubmission MUST include:

- updated release-mode extraction JSON
- updated pdf_oxide overlay image
- updated element crops
- updated comparison JSON / Markdown
- updated `review_bundle.md`
- code diff / test output if any code, preset, ledger, validator, or runner changed

The loop repeats until:

1. release-mode extraction JSON matches the human / WebGPT-approved expected
   page contract, **or**
2. the reviewer stops the loop because the remaining mismatch is a human /
   product decision, **or**
3. the same mismatch persists after two implementation rounds, **or**
4. the fix would broaden beyond the current golden slice.

The project agent may **not** invent a new strategy during the loop. It may
only execute the reviewer's plan, rerun extraction, and return the next ZIP
bundle.

## Closure rule

```text
Human annotation + WebGPT agreement = expected contract.
Project agent execution            = implementation / rerun only.
New ZIP each round                  = evidence.
Deterministic JSON match            = closure for that slice.
```

This is the intent of the iterative loop: human supplies visual truth,
reviewer supplies reasoning and routing, project agent supplies execution
and artifacts, deterministic JSON-match against the agreed expected
contract proves closure.

## Closure signoff artifact (REQUIRED — HTML+CSS annotated page)

When the human or WebGPT requests a final closure signoff for a slice,
the runner MUST produce a self-contained HTML+CSS annotated page:

```text
<out>/images/closure_page.html
```

This artifact is non-negotiable. A slice is **not closed** without it.
A flat PNG, a markdown table, or a comparison summary alone does not
satisfy the contract.

### What the closure_page.html MUST contain

1. **Annotated PDF page.** The rendered `page_clean.png` embedded as a
   base64 data URI, with absolute-positioned color-coded `<div>`
   overlays for every emitted release element.
2. **Summary banner.** A header line at the top with the closure
   statement: matched / missing / ambiguous / unresolved-blocker
   counts, slice id, page index, and (when supplied) the canonical PR
   link.
3. **Color legend.** Visible counts for each color role.
4. **Per-element notes.** A side panel listing every emitted element
   with: block id, emitted type, decision label, text preview, and a
   note. The note MUST be derived from the data files (see "Deterministic
   notes" below). The runner MUST NOT author element-specific narrative.
5. **Cross-linked bboxes ↔ notes.** Hovering or clicking a bbox
   highlights the matching side-panel row, and vice-versa.

### Color contract (per PROJECT_KNOWLEDGE.md §12)

| color   | role                              | drawn? | source of truth                                                                                                  |
|---------|-----------------------------------|--------|------------------------------------------------------------------------------------------------------------------|
| green   | matched expected element          | YES    | `golden_slice_comparison.json` row with `match_status == "matched"` and `best_match_id == el.id`                 |
| yellow  | WAIVED human_decision             | YES    | `mismatches_by_owner.json` `human_decision[]` row with `decision == "accepted_extra_for_GS001"` AND `needs_human_signoff == false` |
| red     | UNRESOLVED BLOCKER                | YES    | anything else (no triage entry, or still-pending human signoff, or unrouted extra)                                |
| (chrome) | page chrome / noise correctly routed | **NO** — filtered | `extra_extractor_triage.json` row with `decision == "accepted_page_chrome_noise"`                                |

**Chrome elements are FILTERED from the closure view.** They are
correctly routed by the preset/ledger layer (e.g. NIST `nist-chrome-001`
typing the DOI watermark to `header_footer_noise`), so showing them on
the closure page adds visual noise without helping the reviewer
verify anything. The chrome count remains in the legend as audit trail
(e.g. "page chrome / noise correctly routed (3) — filtered from this
view"); per-element chrome detail lives in
`json/extra_extractor_triage.json`. The reviewer's job on the closure
page is to verify (a) every human-expected element is matched, (b) every
waiver is intentional, and (c) zero blockers remain.

### Deterministic notes (NO hand-coded element→note mapping)

The runner MUST derive per-element notes solely from:

- `golden_slice_comparison.json` (`rows[]` + `extra_pdf_oxide_elements_not_in_human_label[]`)
- `extra_extractor_triage.json` (`triage_decisions_per_extra[]`)
- `mismatches_by_owner.json` (`human_decision[]` with `decision_basis`, `human_signoff_by`, `human_signoff_at_utc`)
- `expected_elements.json` (for the matched element's `text_hint` / role)

If a note is wrong, the underlying data file is wrong. The runner is
explicitly NOT permitted to embed element-id-specific strings, comments,
or rationale.

### Refusal contract — "not obviously broken"

`closure_page.html` is produced ONLY when the slice is verifiably clean.
The runner MUST refuse and write `closure_refusal.md` instead when ANY
of:

- `comparison.summary.matched_count != expected_element_count`
- `comparison.summary.missing_count > 0`
- `comparison.summary.ambiguous_multiple_count > 0`
- one or more emitted release elements falls into the `blocker` color
  role (no triage entry, OR still-pending human signoff, OR neither
  chrome nor a signed-off waiver)

A refused signoff is itself a useful artifact: it tells the human and
reviewer exactly why the slice is not yet closeable.

### Runner invocation

```bash
python ~/.claude/skills/review-extraction/scripts/build_golden_slice_bundle.py \
  --pdf <pdf> \
  --page-index <idx> \
  --expected-elements <expected.json> \
  --ledger <ledger.json> \
  --slice-id <slice_id> \
  --out <out_dir> \
  --final-signoff \
  --final-signoff-pr-link "https://github.com/<owner>/<repo>/pull/<n>" \
  --zip
```

Notes:

- The runner reads `<out>/json/extra_extractor_triage.json` and
  `<out>/json/mismatches_by_owner.json` by default. Override with
  `--final-signoff-extras-triage` and `--final-signoff-mismatches`.
- The PR link is surfaced only in the closure_page.html sub-line; it
  does not gate the artifact.

### Why this exists

A JSON row can say "matched," but only the page overlay shows whether
the bbox covers the right glyphs, whether a bullet list was partially
matched, or whether an extra block is real visible content. Extraction
quality is **visual**. The closure_page.html is the §12 contract:

> No golden slice closes from tables alone.
> Closure requires a human-readable annotated page plus deterministic release JSON.

### Closure memory upsert (REQUIRED, ArangoDB `/memory`)

The same `--final-signoff` invocation MUST also emit a durable memory
entry ready for ingestion by the `/memory` (ArangoDB) skill:

```text
<out>/json/closure_memory_upsert.json   (schema: review_extraction.closure_memory_upsert.v1)
```

The runner generates this file deterministically alongside
`closure_page.html`. The schema includes:

- `_key`, `kind`, `slice_id`, `page_index`
- `summary` (one-line natural-language closure statement, derived from
  the comparison counts — not hand-authored)
- `tags` (base retrieval handles: `extraction_review`, `golden_slice`,
  `closure`, `<slice_id>`, `page_index_<N>`, `page_1_based_<N+1>`)
- `bridge_keywords` (taxonomy bridges deterministically derived from
  the closure outcome — e.g. `precision`/`verified` when no
  blockers/missing/ambiguous; `loyalty`/`expected_contract` when any
  waivers exist; `resilience`/`preset_routing` when chrome is
  correctly routed; `fragility`/`over_splitting` when residual extras
  remain unrouted)
- `comparison_summary`, `counts_by_color`, `release_element_count`
- `human_decisions` (per-element waivers with signoff identity +
  timestamp, copied from `mismatches_by_owner.json`)
- `triage_summary_by_decision` (per-decision groupings from
  `extra_extractor_triage.json`)
- `pr_link` (when `--final-signoff-pr-link` is supplied)
- `provenance` (paths to the sibling closure artifacts)
- `upsert_hint` (`collection: memory`, `merge_strategy: replace`,
  `_key` matching the top-level `_key`)

**The runner does NOT perform the ArangoDB upsert.** It only writes the
payload. A separate `/memory upsert` invocation (or equivalent ingestion
step) consumes it. This separation keeps the runner pure and lets the
user control when long-term memory is updated.

A slice is not considered closed until BOTH artifacts exist:

1. `<out>/images/closure_page.html` (visual signoff)
2. `<out>/json/closure_memory_upsert.json` (durable memory entry)

If either is missing, the slice is in an incomplete-closure state and
the project agent MUST not declare it closed.

### Self-containment

`closure_page.html` MUST be self-contained: opening the HTML file
directly in a browser (no network, no sibling files required) must
show the visual signoff AND the memory-upsert payload. Concretely:

- The rendered page image (`page_clean.png`) and the human-labeled
  page (`human_labeled_page.png`) are embedded as base64 data URIs.
- The memory-upsert payload appears in TWO places inside the HTML:
  - a hidden `<script type="application/json" id="closure-memory-upsert">`
    block for programmatic ingestion (`document.getElementById("closure-memory-upsert").textContent`),
  - a visible `<details>` block with the pretty-printed JSON for human
    review (and a download link to the sibling
    `json/closure_memory_upsert.json` for convenience).

This rule exists because the closure HTML is the canonical proof
artifact. If anyone opens just the HTML they should see (a) what the
human marked, (b) what the extractor emitted, (c) the per-element
decisions, AND (d) the exact memory entry that captures this closure
for cross-session recall.

## Hard rules

- Do not infer full-document expected counts from one slice.
- Do not set `expected_count = extracted_count`.
- Do not batch before at least one golden slice passes for that family.
- Do not claim `bbox_over_broad` without a deterministic bbox audit.
- Do not call deterministic classifiers “reviewers.”
- Do not claim visual review unless page/crop images are present.
- Do not claim human decision unless a human decision record exists.
- Do not use LLM output to mutate the preset, core code, matrix, or closure state directly.
- Do not call full NIST extraction complete from the risk-candidate matrix alone.

## Relationship to /review-code

Use `/review-extraction` for evidence about document extraction quality.
Use `/review-code` for implementation safety of changed source files.

If a project agent writes new scripts to create the extraction bundle, run both:

```text
/review-extraction  # Is the page/extraction evidence sufficient?
/review-code        # Is the tooling implementation safe?
```

## Relationship to best-practices rules

This skill enforces:

- `agent-no-simulated-review`
- `plan-execution-manifest-not-strategy`
- `plan-reviewed-contract-first`

The boundary to preserve is:

```text
human-visible page != extractor output
hint != finding
classifier != review
review != fix
fix != closure
report != proof
```
