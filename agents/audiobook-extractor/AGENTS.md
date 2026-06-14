---
id: audiobook-extractor
kind: worker
title: Audiobook extractor
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
composes:
- ingest-audiobook
- extract-audiobook
- fact-extractor
- book-extraction-verifier
- best-practices-skills
- code-runner
consult_personas: []
icon: headphones
---

# Audiobook extractor

Runs chapter-aware audiobook extraction and optionally hands clean chapter text
to fact extraction. This worker exists to avoid bespoke audiobook repair scripts.

The worker must use repository skill entrypoints:

- `skills/ingest-audiobook/run.sh` for acquisition/decryption workflows.
- `skills/extract-audiobook/run.sh` for ffprobe chapter discovery, ffmpeg
  splitting, chapter transcription, transcript JSONL, manifests, and resume.
- `skills/fact-extractor/run.sh` for quote-grounded fact extraction from clean
  chapter text.

Do not fork a custom audiobook extraction harness unless the skill itself is
being patched.

## Storage Contract

Use `/mnt/storage12tb/skills/...` for real audiobook/book artifacts by default.
Use `/tmp` only for disposable canaries, prompt tests, or short proof runs. Full
book extraction produces large, expensive-to-regenerate evidence artifacts and
must be durable.

The default full-book output root is:

```text
/mnt/storage12tb/skills/audiobook-extractor/outputs/<book_id>/
```

Supporting skill-specific outputs may live under:

```text
/mnt/storage12tb/skills/extract-audiobook/outputs/<book_id>/
/mnt/storage12tb/skills/fact-extractor/outputs/<book_id>/
```

The worker may copy or generate the primary book-level JSONL artifacts into the
default full-book output root for downstream consumers.

For `facts` mode, maintain a book-level monitoring artifact:

```text
/mnt/storage12tb/skills/fact-extractor/outputs/<book_id>/book_progress.jsonl
```

Call `skills/fact-extractor/run.sh book-progress` with `started`, `running`,
and terminal `accepted` or `failed` chapter states as each chapter moves through
fact extraction. This artifact is append-only and resume-safe. It does not
replace per-chapter `progress.as_completed.jsonl` files.

## Three Primary JSONL Artifacts

For a complete book pipeline, produce exactly these primary book-level JSONL
artifacts:

1. `chapters.jsonl`
   - One record per embedded audiobook chapter.
   - Includes chapter id/title/index, timing, audio path, cleaned text path, and
     transcript JSONL path.
   - Rows must be shaped for later `$memory` `/upsert` into `book_chapters`.

2. `chunks.jsonl`
   - One record per fact-extraction chunk.
   - Must include primary/context spans plus `book`, `book_id`, `chapter`, and
     `chapter_id`.
   - Rows must be shaped for later `$memory` `/upsert` into `book_chunks`.
   - Build with `skills/fact-extractor/run.sh chunk-book` from the audiobook
     `chapters.jsonl`.

3. `accepted_records.jsonl`
   - One record per validated minimal fact/QRA candidate accepted by
     `/fact-extractor`.
   - Rows must be shaped for later `$memory` `/upsert` into `persona_memory`:
     deterministic `_key`, `type`, `record_type`, `memory_collection`,
     `persona_id`, `persona_ids`, `question_text`, `answer_text`, `claim_text`,
     `evidence_text`, `text`, `retrieval_text`, tags, source refs, and
     validation/canon status.
   - Rows must not include inline `embedding`, `embedding_visual`, or `vector`
     fields; `/memory` owns semantic sync and Qdrant metadata on write.
   - Merge per-chapter extraction outputs with
     `skills/fact-extractor/run.sh merge-accepted`.

Per-chapter `transcript_jsonl/chapter_XX.jsonl`, `cleaned_chapters/*.txt`,
`audio_chapters/*.m4a`, prompt payloads, SSE streams, and validation reports are
supporting evidence artifacts, not the three primary book JSONL artifacts.

These three primary JSONL files are extraction artifacts and must be
memory-upsert-compatible, but this worker still does not write them to ArangoDB.
A later ingestion step must batch rows by `memory_collection` and call `/memory`
`/upsert` so semantic sync and recall metadata are handled by the memory
service.

## Mandatory Post-Extraction Verification

Every full-book `facts` extraction must hand off to the
`book-extraction-verifier` worker before the book is reported as memory-ready.
Producing `chapters.jsonl`, `chunks.jsonl`, and `accepted_records.jsonl` is not
enough.

The verifier must prove or repair:

- artifact schema and memory-upsert compatibility
- per-chapter aggregate coverage
- exact quote/source grounding
- ToM tags and graph-edge artifacts
- `$memory` `/upsert` proof when insertion is authorized
- `$memory recall` BM25, semantic/Qdrant, graph, and tag-filter sanity checks

If the verifier finds deterministic repairable defects, the verifier must patch
the responsible code/data artifact or invoke the documented repair command and
rerun its failed checks before returning. A final full-book result may be called
memory-ready only when the verifier emits `sanity_report.json` with critical
checks passed.

## Required Input Contract

- Source audiobook path or source directory containing `audio.m4b`.
- Book metadata: `book` and stable `book_id`.
- Persona metadata when extracting persona facts, for example
  `persona_id=horus_lupercal`.
- Output directory.
- Requested output mode:
  - `chapter-text`: produce clean chapter text only.
  - `transcript-jsonl`: produce timestamped transcript JSONL only.
  - `both`: produce both text and JSONL.
  - `facts`: first produce chapter text, then run `/fact-extractor` with
    `--persona-id` when persona facts are intended, and produce the three
    primary JSONL artifacts.
- Optional bounds: `limit`, `limit_seconds`, model, concurrency.
- Explicit instruction whether memory writes are allowed. Default is no memory
  writes.

## Resume Contract

Resume is mandatory. If interrupted, quit, timed out, or provider/API errors
occur, rerun the same skill command with the same output directory and without
`--force`.

The worker must report:

- existing chapters skipped
- new chapters split/transcribed
- failed chapters and exact artifact paths
- whether the three primary book-level JSONL artifacts are present when the
  requested mode is `facts`
- whether `manifest.json`, `chapters.jsonl`, chapter text, and transcript JSONL
  are present for transcript-only modes

After any durable `extract-audiobook` job, run the implemented runtime verifier
against the extraction output root:

```bash
skills/extract-audiobook/run.sh verify \
  --job-dir /mnt/storage12tb/skills/extract-audiobook/outputs/<book_id>
```

The verifier writes:

```text
/mnt/storage12tb/skills/extract-audiobook/outputs/<book_id>/verify-receipt.json
```

If this command fails, generate the local maintainer packet and stop handoff:

```bash
skills/extract-audiobook/run.sh file-maintainer-ticket \
  --job-dir /mnt/storage12tb/skills/extract-audiobook/outputs/<book_id>
```

Never delete partial outputs unless the human explicitly requests a fresh run or
`--force` is part of the requested command.

## Required Output Contract

- `schema_version`: `audiobook-extractor-result.v1`
- `outcome`: `accepted` | `needs_changes` | `blocked`
- `artifact_root`: output directory
- `manifest`: path to `manifest.json`
- `primary_artifacts`: paths to `chapters.jsonl`, `chunks.jsonl`, and
  `accepted_records.jsonl` when requested mode is `facts`
- `chapter_count`: number of embedded audio chapters
- `completed_chapters`: count with requested artifacts present
- `failed_chapters`: count and ids
- `mode`: requested output mode
- `memory_writes_performed`: false unless explicitly authorized

For `facts` mode, also report the `/fact-extractor` aggregate paths and counts,
the book-level `book_progress.jsonl` path, plus the merged
`accepted_records.jsonl` count. If memory readiness is requested, also report
the `book-extraction-verifier` artifact root, `sanity_report.json`,
`recall_checks.jsonl`, `repair_queue.jsonl`, and final verifier outcome.

## Hard Gates

- Prefer embedded audio chapter metadata over transcript headings.
- If `text.md` has fewer chapter headings than `ffprobe` chapters, treat the
  transcript as missing chapter provenance and regenerate chapter-aware
  transcripts from audio.
- Do not infer chapter ids for facts from a giant flat transcript section.
- Preserve `ffprobe_chapters.json`, `chapters.jsonl`, `manifest.json`, and
  per-chapter artifacts.
- Do not write `persona_memory`, `lessons`, or ArangoDB unless a separate memory
  ingestion task explicitly authorizes it.
- Do not claim memory-upsert-compatible JSONL has already been inserted. Actual
  insertion still requires a separate `/memory` `/upsert` step.
- Do not claim a book extraction is memory-ready until the
  `book-extraction-verifier` worker has run and critical checks have passed.

## Relationship To Other Workers And Skills

- `/extract-audiobook` owns audio-to-transcript artifacts.
- `/fact-extractor` owns quote-grounded fact extraction.
- `/create-qras` or a later normalizer may convert accepted facts to canonical
  QRA/persona-memory records.

## Post-run verification (mandatory when `runtime_self_improvement: substantial`)

When this worker runs a substantial job with a durable output/job directory:

1. Run `skills/extract-audiobook/run.sh verify --job-dir /mnt/storage12tb/skills/extract-audiobook/outputs/<book_id>`.
2. **PASS** → continue handoff.
3. **FAIL** → `skills/extract-audiobook/run.sh file-maintainer-ticket --job-dir /mnt/storage12tb/skills/extract-audiobook/outputs/<book_id>` — do **not** self-commit.

WebGPT review belongs in the **skill-maintainer** cycle, not after every successful run.

Rollout: see `skills/best-practices-skills/references/runtime-self-improvement.md`.
Escalation reference: `skills/extract-audiobook/references/maintainer-escalation.md`.
