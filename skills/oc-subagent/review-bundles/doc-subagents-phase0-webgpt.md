# WebGPT Review Request: doc-extractor and doc-qra Subagents

## Request

Review the proposed `oc-subagent` persona approach for two new source-prep workers:
`doc-extractor` and `doc-qra`. Return exactly one verdict line:

`VERDICT: PASS | NEEDS_CHANGES | BLOCKED`

Then list concrete corrections only. Do not implement fixes. Do not run commands.

## Context

The project is creating persona-dream movie source ingestion support. The goal is
not to create final canon facts directly from messy documents. The workflow should
separate deterministic source preparation, QRA/memory distillation, and later
strict lore extraction.

Existing contracts already read by the project agent:

- `skills/oc-subagent/SKILL.md`: OpenCode child-session subagents with persona
  files under `skills/oc-subagent/personas/<id>/persona.yaml` and a matching
  `pyproject.toml`.
- `skills/extractor/SKILL.md`: runnable Preset-First document extractor for
  PDF/DOCX/HTML/XML/PPTX/XLSX/EPUB/Markdown/images/YouTube, with `--offline`,
  `--fast`, `--sections-only`, `--toc-check`, `--profile-only`, and structured
  extraction outputs.
- `skills/doc2qra/SKILL.md`: runnable document-to-QRA skill. It can run standalone
  or consume extractor output via `--from-extractor`. It stores QRA output to
  ArangoDB database `memory`, collection `lessons`, by `scope`. It warns to run
  one process at a time because each process has its own Chutes concurrency.

Existing `oc-subagent` persona layout includes `extractor/persona.yaml`, which
owns generic structured extraction. The new `doc-extractor` is narrower:
source-prep and section JSONL for downstream lore extraction.

## Proposed Agent Split

### `doc-extractor`

Role:

- Use `$extractor` as the runnable extraction engine.
- Deterministically extract documents into meaningful sections.
- Perform controlled cleanup as an agent.
- Deliver JSONL records, one section per line, for downstream lore/QRA/extraction
  passes.

Owned outputs:

- `sections.jsonl`
- `source-prep-report.json`
- `raw_text` and `cleaned_text` references or inline fields
- raw/clean alignment notes
- source span offsets where available
- source quality labels
- alias candidates and repair notes
- validation warnings

Not owned:

- canonical lore facts
- Theory-of-Mind extraction
- relationship states
- graph upserts
- QRA pair creation
- Arango/Qdrant materialization

Expected JSONL shape:

```json
{
  "schema_version": "persona_source_section.v1",
  "source_id": "horus_lore_doc_001",
  "section_id": "horus_lore_doc_001_s003",
  "section_kind": "scene",
  "source_label": "Betrayer chapter 1 scene 3",
  "raw_text": "...",
  "cleaned_text": "...",
  "start_offset": 1200,
  "end_offset": 2400,
  "detected_entities": ["Horus", "Lorgar", "Angron"],
  "alias_candidates": [
    {"raw": "Lugar", "normalized": "Lorgar", "confidence": 0.96}
  ],
  "repair_notes": [],
  "warnings": []
}
```

Source-prep rules:

- Deterministic first: headings, TOC, timestamps, page spans, paragraph
  boundaries, stable offsets.
- Agent cleanup can normalize obvious transcript/OCR errors, but must preserve
  raw text and repair notes.
- Never silently rewrite messy text into clean canon.
- If a section is too large for downstream QRA/lore extraction, resegment it.
- If offsets or alignment are broken, fail the artifact validation instead of
  claiming source integrity.

### `doc-qra`

Role:

- Use `$doc2qra` as the runnable QRA/memory skill.
- Consume `$extractor` output via `--from-extractor` or consume clean section
  artifacts from `doc-extractor`.
- Produce document summaries and grounded QRA/fact-like memory pairs for recall.
- Store output through the `doc2qra` path in `memory.lessons` using an explicit
  scope.

Owned outputs:

- QRA summary
- QRA pairs
- grounding validation output from `doc2qra`
- memory storage receipt
- `doc-qra-report.json`

Not owned:

- deterministic source extraction
- source cleanup or resegmentation
- final canon lore graph records
- ToM/relationship/style lore extraction
- `sparta_qra` storage

Runtime rules:

- Run one `doc2qra` process at a time.
- Prefer `--dry-run` for review/proof phases before storing.
- Use `--from-extractor` when extractor results are available.
- Do not hand-craft QRA prompts; `doc2qra` requires prompt validation through
  `prompt-lab` before prompt changes.

### Helper Relationship

`doc-qra` may ask `doc-extractor` for bounded help only on source-prep issues,
using the shared skill help syntax:

```text
$ask doc-extractor to resegment source sections with extractor@v1 on artifacts/source-prep/<source_id>
```

Allowed help cases:

- broken offsets
- missing raw span
- over-normalized cleaned text
- ambiguous alias/repair notes
- sections too large or too small
- missing stable section labels

Forbidden help cases:

- asking `doc-extractor` to decide QRA content
- asking `doc-extractor` to validate whether a QRA answer is true
- inventing missing source context
- treating section summaries as source evidence

## Proposed File Changes

Create:

- `skills/oc-subagent/personas/doc-extractor/persona.yaml`
- `skills/oc-subagent/personas/doc-extractor/pyproject.toml`
- `skills/oc-subagent/personas/doc-qra/persona.yaml`
- `skills/oc-subagent/personas/doc-qra/pyproject.toml`

Update:

- `skills/oc-subagent/personas/README.md` to add both personas to the core
  router set and default routes.

## Acceptance Criteria For This Phase

- WebGPT agrees the role boundary is correct or gives concrete corrections.
- Persona files follow `oc_subagent.persona.v1` conventions.
- Every persona lists `memory` in `primary_skills`.
- `doc-extractor` lists `extractor` as a primary skill.
- `doc-qra` lists `doc2qra` as a primary skill.
- `doc-qra` helper policy allows bounded help from `doc-extractor`.
- Neither persona claims ownership of final canonical lore graph extraction.
- Neither persona bypasses deterministic validators or storage receipts.

## Questions For Reviewer

1. Is `doc-extractor` worth adding as a separate top-level persona instead of
   extending the existing generic `extractor` persona?
2. Is `doc-qra` correctly scoped as a QRA/memory distillation worker rather than
   a lore extractor?
3. Is the helper relationship from `doc-qra` to `doc-extractor` sufficiently
   bounded?
4. What concrete persona contract changes are required before implementation?
