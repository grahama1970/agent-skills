---
name: fact-extractor
version: 0.1.0
description: Stage cleaned chapter text and extract quote-grounded minimal fact/QRA candidates from source text or primary/context chunks, with streaming model calls, retries, validation, and durable artifacts.
model: any
category: extraction
tags:
  - extraction
  - facts
  - qra
  - jsonl
  - chutes
  - scillm
entrypoint: ./run.sh
provides:
  - quote-grounded-fact-extraction
  - qra-candidate-extraction
  - extraction-artifact-validation
composes:
  - clean-text
  - scillm
  - create-qras
  - best-practices-python
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-scillm
  - best-practices-arangodb
disciplines:
  - extraction
  - data-engineering
---

# fact-extractor

Use this skill when a project needs source-grounded, recall-useful fact or QRA
candidate extraction from books, chapters, documents, or cleaned text chunks.

This skill creates an intermediate extraction artifact. It does not create
canonical `/create-qras` records, does not write `persona_memory`, does not write
`lessons`, and does not upsert to ArangoDB.

## Contract

The model-owned output is minimal JSONL. Each line must contain exactly:

```json
{"question":"string","answer":"string","claim":"string","evidence_quote":"exact quote","factuality":"narration_assertion|character_speech|character_thought|reported_story|uncertain_narration","tom":null}
```

For non-null theory-of-mind records, `tom` must contain exactly:

```json
{"holder":"string","mental_state":"belief|intention|emotion|perception|preference|uncertainty|evaluation","target":"string"}
```

The skill is responsible for deterministic cleaning/staging, chapter metadata,
chunk spans, validation, retry degradation, and artifact preservation.

## Required Behavior

- Split source text into paragraph-aware, sentence-boundary-safe chunks.
- Stage raw book/audiobook transcript sources into normalized chapter text files
  before extraction when the source has not already been cleaned.
- Render overlap as `<context_before>`, `<primary_text>`, and
  `<context_after>`.
- Instruct the model to copy every `evidence_quote` from `primary_text` only.
- Use streaming Chutes/scillm-compatible chat completion calls.
- Preserve each rendered prompt payload, raw SSE stream, parsed model JSONL,
  validation report, accepted records, aggregate report, and status file.
- Validate JSONL shape, exact quote grounding, primary-text quote origin, closed
  factuality vocabulary, theory-of-mind shape, duplicate records, HTTP status,
  and stream completion.
- Treat density misses as warnings unless the record count is zero or exceeds
  the configured hard cap.
- Retry failed chunks with lower output pressure.
- Resume by skipping chunks with existing `accepted_records.jsonl` unless
  `--force` is supplied.
- Enrich every accepted record with deterministic `book`, `chapter`,
  `chapter_id`, `chunk_id`, source SHA, primary/context spans, and absolute
  evidence quote spans. Aggregate validation must fail if accepted records lack
  this metadata.

## Commands

Stage a raw book transcript into cleaned chapter files:

```bash
skills/fact-extractor/run.sh stage-book ./Galaxy_in_Flames/text.md \
  --book "Galaxy in Flames" \
  --book-id galaxy_in_flames \
  --out /mnt/storage12tb/skills/fact-extractor/staged/galaxy_in_flames \
  --force
```

For audiobook source directories, prefer `text.md` when present. Do not use
overlapping `clean/*.json` fragments as chapter inputs unless no coherent text
source exists.

Run a full chapter extraction:

```bash
skills/fact-extractor/run.sh chapter ./chapter_02.txt \
  --book "Horus Rising" \
  --chapter "Chapter 02" \
  --chapter-id horus_rising_ch02 \
  --persona-id horus_lupercal \
  --out /mnt/storage12tb/skills/fact-extractor/outputs/horus_rising_ch02 \
  --target-chars 3500 \
  --max-chars 4500 \
  --concurrency 1
```

Create chunks only:

```bash
skills/fact-extractor/run.sh chunk ./chapter_02.txt \
  --out /tmp/chapter_02_chunks.jsonl \
  --document-id horus_rising_ch02
```

Create a book-level chunks artifact from an audiobook extraction manifest:

```bash
skills/fact-extractor/run.sh chunk-book \
  --chapters /mnt/storage12tb/skills/extract-audiobook/outputs/galaxy_in_flames/chapters.jsonl \
  --out /mnt/storage12tb/skills/audiobook-extractor/outputs/galaxy_in_flames/chunks.jsonl \
  --book "Galaxy in Flames" \
  --book-id galaxy_in_flames
```

Append a book-level chapter progress event from a per-chapter extraction output:

```bash
skills/fact-extractor/run.sh book-progress \
  --book-root /mnt/storage12tb/skills/fact-extractor/outputs/galaxy_in_flames \
  --chapter-out /mnt/storage12tb/skills/fact-extractor/outputs/galaxy_in_flames/chapter_01 \
  --book "Galaxy in Flames" \
  --book-id galaxy_in_flames \
  --chapter "Chapter 01" \
  --chapter-id galaxy_in_flames_ch01 \
  --status running
```

Extract from existing chunk JSONL:

```bash
skills/fact-extractor/run.sh extract \
  --chunks /tmp/chapter_02_chunks.jsonl \
  --out /mnt/storage12tb/skills/fact-extractor/outputs/horus_rising_ch02 \
  --book "Horus Rising" \
  --chapter "Chapter 02" \
  --chapter-id horus_rising_ch02 \
  --persona-id horus_lupercal
```

Check dependencies and executable wiring:

```bash
skills/fact-extractor/run.sh doctor --json
```

Merge per-chapter extraction outputs into a book-level accepted facts artifact:

```bash
skills/fact-extractor/run.sh merge-accepted \
  /mnt/storage12tb/skills/fact-extractor/outputs/galaxy_in_flames \
  --out /mnt/storage12tb/skills/audiobook-extractor/outputs/galaxy_in_flames/accepted_records.jsonl
```

## Runtime Defaults

- Default URL: `http://localhost:4001/v1/chat/completions`
- Default auth token: `SCILLM_PROXY_TOKEN`, then `CHUTES_PROXY_TOKEN`, falling
  back to `sk-dev-proxy-123` for the local dev proxy.
- Default model field: `chutes-deepseek`; override with any scillm one-shot
  chat model such as `gemini-flash`, `gpt-5.5`, or `moonshot-text` when auth is
  healthy.
- Default temperature: `0`
- Default streaming: `true`
- Default concurrency: `1`
- Default retry ladder: `8-12`, then `5-8`, then `2-4` records.
- Default `max_tokens`: omitted. Pass `--max-tokens N` only when a specific
  model/provider needs an explicit completion cap.

## Output Artifacts

The output directory contains:

- `stage_manifest.json` when `stage-book` is used
- `cleaned_chapters/chapter_XX.txt` when `stage-book` is used
- `chunks.jsonl`
- `book_progress.jsonl` at a book output root when full-book orchestration calls
  `book-progress`
- `run_manifest.json`
- `progress.as_completed.jsonl`
- `aggregate_report.json`
- `accepted_records.jsonl`
- `status.md`
- `chunks/<chunk_id>/input_chunk_metadata.json`
- `chunks/<chunk_id>/accepted_records.jsonl`
- `chunks/<chunk_id>/attempt_XX/prompt_payload.json`
- `chunks/<chunk_id>/attempt_XX/stream.raw.sse`
- `chunks/<chunk_id>/attempt_XX/model_content.raw.jsonl`
- `chunks/<chunk_id>/attempt_XX/validation_report.json`

For full-book audiobook pipelines, the primary durable JSONL artifacts are:

- `chapters.jsonl`: one chapter provenance record per embedded audio chapter.
  Rows are shaped for later `$memory` `/upsert` into `book_chapters`.
- `chunks.jsonl`: one fact-extraction chunk record per primary/context span,
  enriched with `book`, `book_id`, `chapter`, and `chapter_id`.
  Rows are shaped for later `$memory` `/upsert` into `book_chunks`.
- `accepted_records.jsonl`: one validated extraction candidate per accepted
  fact/QRA-like record, merged from per-chapter fact extraction outputs. Rows
  are shaped for later `$memory` `/upsert` into `persona_memory` when
  `--persona-id` is supplied.

Store full-book artifacts under `/mnt/storage12tb/skills/...` by default. Use
`/tmp` only for disposable canaries, prompt experiments, or short proof runs.
The primary JSONL artifacts are memory-upsert-compatible, but this skill still
does not perform the write. Rows include deterministic `_key`, `type`,
`record_type`, `memory_collection`, `text`, `retrieval_text`, tags, source refs,
and status fields. Accepted fact rows also include `persona_id`,
`question_text`, `answer_text`, `claim_text`, and `evidence_text`. Rows must not
include inline `embedding`, `embedding_visual`, or `vector` fields. Later
ingestion should batch rows by `memory_collection` and write through `/memory`
`/upsert` so semantic sync and Qdrant metadata are handled by the memory
service.

The aggregate report always includes:

- `schema_version`
- `accepted`
- `completed_chunks`
- `accepted_chunks`
- `failed_chunks`
- `total_records`
- `accepted_record_metadata_ok`
- `accepted_record_metadata_defects`
- `memory_writes_performed: false`
- `forbidden_writes: ["persona_memory", "lessons", "arangodb"]`

The book-level progress artifact is append-only JSONL. Each row has
`schema_version: fact-extractor-book-progress.v1`, `book`, `book_id`,
`chapter`, `chapter_id`, `status`, chunk/record counts, timestamp fields,
artifact paths, `memory_writes_performed: false`, and the same forbidden-write
list. It is a monitoring artifact only and must not replace per-chapter
`progress.as_completed.jsonl`.

## Relationship To Other Skills

- `/create-qras` creates canonical QRA records. This skill creates validated
  source-grounded extraction candidates.
- A later normalizer can convert accepted candidates to canonical QRA or
  `persona_memory` schemas.
- A later memory upserter can ingest reviewed records. This skill must not
  perform that write.
