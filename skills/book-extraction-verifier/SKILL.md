---
name: book-extraction-verifier
description: >
  Verify a completed full-book audiobook/fact extraction before it is called
  memory-ready. Use when a book has chapters.jsonl, chunks.jsonl, and
  accepted_records.jsonl artifacts and needs post-extraction sanity checks,
  ArangoDB memory-upsert proof, BM25 recall checks, semantic/Qdrant recall
  checks, graph recall checks, theory-of-mind checks, or a concrete repair
  queue.
triggers:
  - verify extracted book
  - run book extraction sanity checks
  - check book memory readiness
  - verify book recall
  - run post-extraction verifier
provides:
  - book-extraction-verification
  - memory-readiness-report
  - recall-sanity-checks
  - extraction-repair-queue
composes:
  - memory
  - fact-extractor
  - audiobook-extractor
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-arangodb
taxonomy:
  - validation
  - precision
  - resilience
---

# Book Extraction Verifier

Use this skill after a full-book `facts` extraction. It verifies that book-level
artifacts are shaped for memory, source-grounded, ToM/graph-ready, and recallable
through `$memory` when live checks are requested.

## Entry Point

Run:

```bash
skills/book-extraction-verifier/run.sh verify-book \
  --book-id galaxy_in_flames \
  --book "Galaxy in Flames" \
  --persona-id horus_lupercal \
  --book-root /mnt/storage12tb/skills/audiobook-extractor/outputs/galaxy_in_flames \
  --fact-root /mnt/storage12tb/skills/fact-extractor/outputs/galaxy_in_flames \
  --require-memory
```

Default output root:

```text
/mnt/storage12tb/skills/book-extraction-verifier/outputs/<book_id>/
```

The command writes:

- `sanity_report.json`
- `sanity_report.md`
- `recall_checks.jsonl`
- `repair_queue.jsonl`

## Hard Rules

- Do not call a book memory-ready unless `sanity_report.json` has
  `critical_checks_passed=true`.
- Do not write raw AQL or import `ArangoClient`. Use `$memory` HTTP endpoints
  only.
- Do not write inline `embedding`, `embedding_visual`, or `vector` fields.
- Do not treat successful extraction as successful recall.
- Do not treat memory upsert as graph proof.
- If `repair_queue.jsonl` is nonempty, patch or invoke the listed repair command
  before reporting success.

## Checks

The verifier checks:

- `chapters.jsonl`, `chunks.jsonl`, `accepted_records.jsonl`, and optional
  `persona_memory_edges.jsonl` parse as JSONL.
- Required `_key` values are unique.
- Rows have `memory_collection` where required.
- Accepted records include `book_id`, `chapter_id`, `chunk_id`, `persona_id`,
  QRA text fields, retrieval text, source refs, and required tags.
- Evidence quotes are exact substrings of the chunk primary text. Local chunk
  ids such as `c01` are resolved via `chapter_id` to full chunk ids such as
  `<chapter_id>-c01`.
- Non-null `tom` records have `tom_tags` and `tom_state_type`.
- ToM graph edges refer to existing `persona_memory` records.
- When `--require-memory` is passed, `/memory` `/health` is checked and recall
  fixtures are run through `/recall`.

## Fixture File

Pass `--fixture-path fixtures.jsonl` to define live recall checks. Each line:

```json
{"id":"bm25_example","kind":"bm25","q":"query text","expected_key":"record_key","require_dense":false,"require_graph":false}
```

If no fixture file is supplied, the verifier generates deterministic fixtures
from accepted records and ToM edges. Generated fixtures are useful for sanity,
but curated fixtures are preferred for release gates.
