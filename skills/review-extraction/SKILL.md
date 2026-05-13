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
```

If `optional_code/` exists, the artifact review is not enough. The changed code
also needs a separate `/review-code` review.

## Required manifest fields

`manifest.json` MUST include:

```json
{
  "schema_version": "review_extraction.golden_slice.v1",
  "slice_id": "nist_page_28_printed_page_1",
  "source_pdf": "...",
  "human_claim": "PDF page 28",
  "zero_based_page_index": 27,
  "one_based_pdf_page_number": 28,
  "printed_page_label": "PAGE 1",
  "created_at": "...",
  "created_by": "...",
  "release_mode": true,
  "apply_mode": "release",
  "staging_entries_used": false,
  "llm_used": false,
  "code_or_preset_mutated": false,
  "matrix_mutated": false
}
```

## Required comparison table

`tables/golden_slice_comparison.md` MUST include these columns:

```text
expected_family
human_label
pdf_oxide_emitted
emitted_id
emitted_type
source_type_or_block_type
bbox_match
text_match
notes
owner_if_wrong
next_step
```

Allowed `owner_if_wrong` values:

```text
no_change
pdf_oxide_core
nist_preset_ledger
downstream_semantic_parser
second_pass_visual_adjudicator
human_decision
```

## Golden-slice review protocol

1. **Human labels representative page(s).**
   The human identifies visible expected elements such as headers, headings,
   paragraphs, bullet lists, footnotes, figures, tables, callouts, or requirements.

2. **Project agent produces evidence only.**
   The project agent renders the page, runs release-mode extraction, generates overlay
   images, crops, JSON, and comparison tables. It must not patch code or mutate status.

3. **Reviewer compares expected vs actual.**
   The reviewer answers:
   - Did pdf_oxide emit the expected element?
   - Is the type correct?
   - Is the bbox/crop correct?
   - Is the text/payload correct?
   - If wrong, who owns the fix?

4. **Only after review may fixes happen.**
   Approved fixes become separate tasks:
   - core extractor change,
   - preset/ledger rule,
   - downstream semantic parser change,
   - prompt/validator change,
   - human decision fixture.

5. **Deterministic rerun proves closure.**
   No status changes without rerun, fixture, and gate proof.

## Review output format

The reviewer should return:

```text
Verdict: APPROVE_EVIDENCE | NEEDS_MORE_EVIDENCE | REJECT_BUNDLE

Page identity:
- zero-based page index:
- one-based PDF page:
- printed label:

Extraction summary:
- expected elements:
- matched:
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

Next action:
- one concrete action only
```

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
