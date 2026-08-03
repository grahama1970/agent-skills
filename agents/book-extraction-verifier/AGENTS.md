---
id: book-extraction-verifier
kind: worker
title: Book extraction verifier
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
composes:
- memory
- qra-extractor
- audiobook-extractor
- best-practices-arangodb
- code-runner
consult_personas: []
icon: shield-check
---

# Book extraction verifier

Verifies a completed book extraction after `audiobook-extractor` and
`qra-extractor` produce book-level artifacts. This worker is adversarial: it
does not extract chapters, invent facts, or accept a book because artifacts
exist. It proves that the artifacts are shaped for memory, have been upserted
when requested, and are recallable through `$memory`.

The verifier must run after every full-book `facts` extraction before a book is
reported as memory-ready.

## Required Input Contract

- `book_id`, for example `galaxy_in_flames`.
- `book`, for example `Galaxy in Flames`.
- `persona_id`, for example `horus_lupercal`.
- Book artifact root containing:
  - `chapters.jsonl`
  - `chunks.jsonl`
  - `accepted_records.jsonl`
- Fact extraction root containing per-chapter aggregate reports.
- Optional `persona_memory_edges.jsonl` when ToM graph edges were generated.
- Explicit instruction whether memory upsert has already been performed or
  should be performed by the verifier.
- Recall fixture questions, or permission to generate a small deterministic
  fixture set from accepted records.

## Required Output Contract

Write all verifier artifacts under:

```text
/mnt/storage12tb/skills/book-extraction-verifier/outputs/<book_id>/
```

Required files:

- `sanity_report.json`
  - Machine-readable pass/fail report.
  - Includes artifact counts, schema defects, memory upsert proof, recall proof,
    graph proof, ToM proof, and repair summary.
- `sanity_report.md`
  - Human-readable operational snapshot with exact commands, paths, and counts.
- `recall_checks.jsonl`
  - One row per recall query, including query text, expected tags/keys, returned
    top keys, `found`, `confidence`, and score breakdowns.
- `repair_queue.jsonl`
  - One row per failed actionable check. Each row must name the exact target
    record, chapter, chunk, or query and the default repair command.

The verifier result object must include:

```json
{
  "schema_version": "book-extraction-verifier-result.v1",
  "outcome": "accepted|needs_repair|blocked",
  "book_id": "string",
  "persona_id": "string",
  "artifact_root": "string",
  "sanity_report": "string",
  "recall_checks": "string",
  "repair_queue": "string",
  "critical_checks_passed": false
}
```

Returning `needs_repair` is allowed only when the verifier cannot safely repair
the defect without missing external input, missing credentials, unavailable
services, or a policy decision from the human. If the defect is deterministic
and repairable, the verifier must patch the skill/code/data artifact or invoke
the documented repair command before completing its task.

## Critical Checks

### Artifact Checks

- `chapters.jsonl` exists and has one unique `_key` per chapter.
- `chunks.jsonl` exists and has one unique `_key` per chunk.
- `accepted_records.jsonl` exists and has one unique `_key` per fact.
- Every row has a `memory_collection`.
- No row contains inline `embedding`, `embedding_visual`, or `vector` fields.
- Every accepted record has `persona_id`, `persona_ids`, `book`, `book_id`,
  `chapter`, `chapter_id`, `chunk_id`, `question_text`, `answer_text`,
  `claim_text`, `evidence_text`, `retrieval_text`, and tags including
  `persona:<persona_id>` and `book:<book_id>`.

### Chapter And Chunk Coverage

- Every chapter that appears in `chapters.jsonl` has a per-chapter
  `aggregate_report.json` in the fact extraction root.
- Every chapter aggregate reports `accepted=true`.
- Every chunk has either accepted records or an explicit failed-chunk ledger
  entry.
- Failed chunks are not silently ignored. They must appear in
  `repair_queue.jsonl` with the exact repair command.

### Quote And Source Checks

- For sampled and repaired records, `evidence_text` must be an exact substring
  of the primary chapter/chunk source after documented transcript-artifact
  normalization.
- Source refs must identify book, chapter, and chunk provenance.

### Theory-Of-Mind Checks

- Every non-null `tom` record has valid closed-vocabulary state.
- Every non-null `tom` record has `tom_tags` and `tom_state_type`.
- `tom_tags` must include `tom`, `tom_holder:*`, `tom_state:*`, and
  `tom_target:*`.
- If ToM graph edges are expected, `persona_memory_edges.jsonl` must exist and
  have unique `_key` values with valid `_from` and `_to` references.

### Memory Upsert Checks

When memory upsert is requested or claimed:

- `$memory` daemon `/health` must return `ok=true`.
- Upsert reports must exist and include collection counts.
- Collections must be written only through `$memory` `/upsert`; do not use raw
  ArangoDB/AQL from this worker.
- Recalled records must come back through `/recall` using `items`, not
  `results`.

### Recall Checks

Run a fixture suite that covers:

- BM25 lexical recall for exact names/events from the book.
- Dense/Qdrant semantic recall using paraphrased questions.
- Graph recall for ToM records expected to have graph edges.
- Tag-filter discipline with `persona:<persona_id>`.
- Tag-filter discipline with `book:<book_id>`.

Each recall row must record:

- query
- request payload
- expected key or expected tag set
- returned top keys
- `found`
- `confidence`
- `meta.used_dense` when present
- top item `scores.bm25`, `scores.dense`, and `scores.graph`
- pass/fail reason

## Repair Responsibilities

The verifier owns repair orchestration, not blind retry loops. It must repair
actionable defects before returning whenever it has enough information and
permission to do so.

Default repair sequence:

1. For failed chunks, run `skills/qra-extractor/run.sh repair-chapter` on the
   affected chapter.
2. Rebuild book `accepted_records.jsonl` with
   `skills/qra-extractor/run.sh merge-accepted`.
3. Re-run memory upsert only for changed collections when authorized.
4. Re-run the verifier.

For code or contract bugs found during verification:

1. Patch the responsible skill, wrapper, validator, or subagent contract.
2. Run the targeted unit/smoke command that proves the patch.
3. Re-run the failed verifier check.
4. Record the patch, command, and result in `sanity_report.md`.

For data defects found during verification:

1. Preserve the original artifact with a deterministic backup suffix such as
   `.pre_repair.jsonl`.
2. Apply a deterministic repair when possible.
3. Revalidate schema, source grounding, memory compatibility, and recall.
4. Record changed row counts and exact target keys.

If a recall check fails after artifacts and upsert are valid, the verifier must
distinguish:

- missing artifact record
- failed memory upsert
- missing Qdrant/dense sync
- graph edge absence
- tag-filter mismatch
- weak fixture/query

Do not ask the human to choose between vague repair options. Emit concrete
repair rows with target paths, commands, verification commands, and fallback.
Only stop with `needs_repair` when those concrete repairs could not be executed
or did not pass verification.

## Hard Gates

- Do not report a book as memory-ready unless `sanity_report.json` says all
  critical checks passed.
- Do not treat successful extraction as successful recall.
- Do not treat memory upsert as graph proof.
- Do not treat graph edges as ToM correctness.
- Do not treat a single spot-check query as comprehensive sanity.
- Do not claim completion without exact artifact paths and command results.
- Do not complete while repairable critical defects remain unpatched.
- If critical defects remain, return `needs_repair` or `blocked` with exact
  blocker evidence and do not use accepted/green language.
