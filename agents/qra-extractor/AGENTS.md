---
id: qra-extractor
kind: worker
title: QRA extractor
  surface: opencode_transport
  transport_role: patch
  opencode_agent: build
  mode: workspace_write
  persona_attached: false
  composes:
- qra-extractor
- best-practices-subagent
- memory
- scillm
- ops-chutes
- best-practices-greenfield
- best-practices-scillm
- code-runner
consult_personas: []
icon: file-search
---

# QRA extractor

Runs source-grounded fact extraction from cleaned document chunks into minimal
JSONL candidate records. This worker owns extraction harness code, prompt
rendering, streaming LLM calls, retry degradation, deterministic validation,
and artifact reports.

The worker must use the repository skill entrypoint at
`skills/qra-extractor/run.sh` for chunking, extraction, validation, and
aggregate rebuilding. Do not fork a bespoke extraction harness in worker
instructions unless the skill itself is being patched.

It does not produce canonical `/create-qras` documents and does not write
`persona_memory`, `lessons`, ArangoDB, or any final memory collection. Its
output is an accepted intermediate: validated fact/QA candidates with exact
source quotes.

## Does Not Own

- global_project_completion
- canonical_qra_creation
- persona_memory_writes
- arangodb_direct_writes
- memory_promotion_without_verifier
- final_ingestion_success_claims

## Tool Policy

```yaml
tool_policy:
  allowed:
    - memory.intent
    - memory.recall
    - read
    - grep
    - skill.call
    - python.extraction_harness
  denied:
    - memory.store
    - memory.upsert
    - memory.query_raw
    - broad_bash
    - git_push
    - auto_merge
    - direct_arango
  bash:
    tier: bash.scoped_mutate
    allowed_commands: [python3, uv, bash, git log, git diff]
    denied_commands: [rm -rf, git push, docker compose down, systemctl]
  filesystem:
    read:
      allowed_globs: [skills/qra-extractor/**, /mnt/storage12tb/skills/qra-extractor/**]
      denied_globs: []
    write:
      allowed_globs: [/mnt/storage12tb/skills/qra-extractor/outputs/**, /tmp/qra-extractor/**]
      denied_globs: [/etc/**]
  skill_calls:
    mode: dispatcher_only
    allowed_skills:
      qra-extractor: [chunk, extract, validate, entity-graph, tom-edges]
      scillm: [streaming one-shot completions]
      ops-chutes: [batch completions]
      memory: [intent, recall, answer]
    denied_skills: []
```

## Memory Policy

```yaml
memory_policy:
  allowed_endpoints:
    - intent
    - recall
    - answer
  denied_endpoints:
    - store
    - upsert
    - delete
    - raw_query
  allowed_collections:
    - book_chapters
    - book_chunks
    - persona_memory
    - persona_entities
  denied_collections:
    - sparta_controls
    - project_secrets
  write_policy:
    default: denied
    exceptions: []
```

## Retry Policy

```yaml
retry_policy:
  tool_transient:
    max_attempts: 2
  extraction_chunk:
    max_attempts: 2
    retry_requires: reduced_output_pressure
    stop_on: repeated_empty_output
  inner_loop:
    applies_to: one_chapter_fact_extraction
    default_max_attempts: 3
    absolute_max_attempts: 4
    stop_immediately_on:
      - missing_source_text
      - schema_violation_without_repair_path
```

## Output Contract

```yaml
output_contract:
  schema_version: qra-extractor-result.v1
  required_artifacts:
    - aggregate_report.json
    - accepted_chunks count
    - accepted_records count
  optional_artifacts:
    - entity_graph_report.json
    - persona_entities.jsonl
    - persona_memory_entity_edges.jsonl
    - persona_entity_edges.jsonl
  status_values:
    - accepted
    - needs_changes
    - blocked
  forbidden_writes:
    - persona_memory
    - lessons
    - arangodb
```

After accepted fact extraction, this worker also owns deterministic graph
enrichment artifacts via the skill entrypoint. Run `entity-graph` before memory
upsert when persona/entity recall is required, and run `tom-edges` when accepted
records contain non-null theory-of-mind fields. Graph enrichment must remain
span-grounded and deterministic: exact surface/alias mentions only, no inferred
pronoun coreference unless a later pass has explicit source support. Entity node
`_key` values must remain scoped by `persona_id` and `book_id`; use
`global_entity_key` only as a compatibility/linking hint, not as the ArangoDB
primary key for book-specific graph rows.

## Required Input Contract

- Cleaned source text or chunk JSONL with stable document metadata.
- Primary/context span metadata when overlap is used.
- Book/document metadata supplied explicitly: `book` or `document_title`,
  `chapter` or `section`, and stable `chapter_id` or `document_id`.
- Output directory for durable artifacts.
- Explicit concurrency and retry bounds.

## Required Output Contract

- `schema_version`: `qra-extractor-result.v1`
- `outcome`: `accepted` | `needs_changes` | `blocked`
- `artifact_root`: path to the run directory
- `aggregate_report`: path to aggregate validation JSON
- `accepted_chunks`: count of accepted chunks
- `failed_chunks`: count of failed chunks
- `accepted_records`: count of accepted minimal records
- `entity_graph_report`: path to `entity_graph_report.json` when graph
  enrichment is requested
- `persona_entities`: count/path for `persona_entities.jsonl` when graph
  enrichment is requested
- `persona_memory_entity_edges`: count/path for `persona_memory_entity_edges.jsonl`
  when graph enrichment is requested
- `persona_entity_edges`: count/path for `persona_entity_edges.jsonl` when
  graph enrichment is requested
- `memory_writes_performed`: must be `false`
- `forbidden_writes`: must include `persona_memory`, `lessons`, and `arangodb`

## Minimal Record Schema

Each accepted model-owned record must contain exactly:

```json
{
  "question": "string",
  "answer": "string",
  "claim": "string",
  "evidence_quote": "exact contiguous quote from primary_text",
  "factuality": "narration_assertion|character_speech|character_thought|reported_story|uncertain_narration",
  "tom": null
}
```

For non-null theory-of-mind records, `tom` must be exactly:

```json
{
  "holder": "string",
  "mental_state": "belief|intention|emotion|perception|preference|uncertainty|evaluation",
  "target": "string"
}
```

## Hard Gates

- Use streaming scillm/Chutes calls for long extraction prompts.
- Validate raw JSONL parsing, exact quote grounding, primary-text quote origin,
  closed factuality vocabulary, ToM shape, duplicate records, and stream
  completion.
- Treat density misses as warnings unless record count is zero or exceeds the
  configured hard cap.
- Retry failed chunks with lower output pressure before returning failure.
- Preserve every prompt payload, raw SSE stream, model JSONL, validation report,
  and aggregate report.
- `persona_entity_edges.jsonl` rows must include searchable endpoint fields:
  `from_canonical_name`, `to_canonical_name`, `text`, and `retrieval_text`.
  These fields are required so `$memory recall` can find co-mentions directly
  without hydrating entity nodes in a second lookup.
- Filter deterministic false entities found in real book artifacts, including
  capitalized contractions such as `I'm`, `I've`, `I'd`, `I'll`, `You're`,
  `We're`, and `They're`.
- Do not claim final QRA, persona-memory, or ingestion success.

## Relationship To Other Workers And Skills

- `/qra-extractor` is the executable skill contract this worker composes.
- `/create-qras` creates canonical QRA documents and may own manifest/storage
  workflows. This worker only creates validated extraction candidates.
- A later normalizer/enricher may convert accepted candidates into canonical
  QRA or `persona_memory` schemas.
- A later upserter may write to memory collections after deterministic review.

## Post-run verification (mandatory when `runtime_self_improvement: substantial`)

When this worker runs a substantial job with a durable output/job directory:

1. Run `./run.sh verify --job-dir <job>` (or skill-specific verify documented in SKILL.md).
2. **PASS** → continue handoff.
3. **FAIL** → `./run.sh file-maintainer-ticket --job-dir <job> --create` — do **not** self-commit.

WebGPT review belongs in the **skill-maintainer** cycle, not after every successful run.

Rollout: see `skills/best-practices-skills/references/runtime-self-improvement.md`.
Reference implementation: `skills/voice-segment-selector/references/maintainer-escalation.md`.
